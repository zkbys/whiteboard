#!/usr/bin/env python3
"""Create a browser-based bbox calibration tool for whiteboard board images."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix() if path.resolve().is_relative_to(root.resolve()) else path.resolve().as_posix()


def browser_relpath(path: Path, html_dir: Path) -> str:
    return Path(relpath(path, html_dir)).as_posix() if path.resolve().is_relative_to(html_dir.resolve()) else Path("../../").joinpath(path.resolve()).as_posix()


def copy_board_image(image_path: Path | None, board_id: str, html_dir: Path) -> str:
    if not image_path or not image_path.exists():
        return ""
    assets_dir = html_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    suffix = image_path.suffix or ".png"
    dest = assets_dir / f"{board_id}{suffix}"
    if image_path.resolve() != dest.resolve():
        shutil.copy2(image_path, dest)
    return dest.relative_to(html_dir).as_posix()


def find_asset_boards(asset_manifest: dict[str, Any], project: Path) -> dict[str, dict[str, Any]]:
    boards: dict[str, dict[str, Any]] = {}
    for item in asset_manifest.get("boards", []) or []:
        board_id = item.get("boardId") or item.get("id")
        asset = item.get("asset") or {}
        if not board_id:
            continue
        uri = asset.get("uri") or asset.get("src")
        image_path = project / uri if uri else None
        boards[str(board_id)] = {
            "boardId": str(board_id),
            "title": item.get("title") or str(board_id),
            "asset": asset,
            "imagePath": image_path,
            "width": asset.get("width"),
            "height": asset.get("height"),
        }
    return boards


def spec_paths_from_plan(project: Path, plan: dict[str, Any]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for board in plan.get("boards", []) or []:
        board_id = board.get("id") or board.get("boardId")
        path = board.get("boardSpecPath")
        if board_id and path:
            out[str(board_id)] = project / path
    return out


def fallback_spec_paths(project: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in sorted((project / "infographic" / "board_specs").glob("*.json")):
        stem = path.name.replace(".board_spec.json", "").replace(".json", "")
        out[stem] = path
    return out


def element_candidates(spec: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    title = spec.get("title")
    if title:
        items.append({"id": "title", "label": title, "kind": "title", "role": "title"})
    seen = {item["id"] for item in items}

    for raw in spec.get("elements", []) or []:
        element_id = raw.get("id")
        if not element_id or element_id in seen:
            continue
        items.append(
            {
                "id": str(element_id),
                "label": raw.get("text") or raw.get("label") or str(element_id),
                "kind": raw.get("kind") or raw.get("role") or "element",
                "role": raw.get("role"),
                "bbox": raw.get("bbox"),
                "annotationTargetBbox": raw.get("annotationTargetBbox"),
            }
        )
        seen.add(str(element_id))

    for raw in spec.get("keyObjects", []) or []:
        element_id = raw.get("id")
        if not element_id or element_id in seen:
            continue
        items.append(
            {
                "id": str(element_id),
                "label": raw.get("label") or raw.get("text") or str(element_id),
                "kind": raw.get("role") or "element",
                "role": raw.get("role"),
            }
        )
        seen.add(str(element_id))
    return items


def load_existing_calibration(calibration_dir: Path, board_id: str) -> dict[str, Any] | None:
    candidates = [
        calibration_dir / f"{board_id}.element_bboxes.json",
        calibration_dir / f"{board_id}.json",
    ]
    for path in candidates:
        if path.exists():
            return read_json(path)
    return None


def load_auto_prefill(prefill_path: Path | None) -> dict[str, dict[str, Any]]:
    """Load auto-calibration report and map element id -> prefill record."""
    if not prefill_path or not prefill_path.exists():
        return {}
    try:
        data = read_json(prefill_path)
    except (OSError, json.JSONDecodeError):
        return {}
    prefill: dict[str, dict[str, Any]] = {}
    for board in data.get("boards") or []:
        board_id = str(board.get("boardId", ""))
        if not board_id:
            continue
        prefill[board_id] = {}
        calibration_file = board.get("calibrationFile")
        if calibration_file:
            candidates = [
                prefill_path.parent / calibration_file,
                prefill_path.parent.parent / calibration_file,
            ]
            cal_path = next((p for p in candidates if p.exists()), None)
            if cal_path:
                cal = read_json(cal_path)
                for element in cal.get("elements") or []:
                    element_id = element.get("id")
                    if element_id and element.get("bbox"):
                        prefill[board_id][str(element_id)] = dict(element)
                continue
        # Fallback: use matched ids reported in the auto report.
        for element_id in board.get("matchedIds") or []:
            prefill[board_id][str(element_id)] = {"id": element_id}
    return prefill


def build_config(
    project: Path,
    asset_manifest_path: Path,
    infographic_plan_path: Path,
    calibration_dir: Path,
    html_dir: Path,
    prefill_path: Path | None = None,
) -> dict[str, Any]:
    asset_manifest = read_json(asset_manifest_path)
    plan = read_json(infographic_plan_path) if infographic_plan_path.exists() else {"boards": []}
    assets = find_asset_boards(asset_manifest, project)
    spec_paths = spec_paths_from_plan(project, plan) or fallback_spec_paths(project)
    auto_prefill = load_auto_prefill(prefill_path)

    boards = []
    for board_id in sorted(set(assets) | set(spec_paths)):
        if board_id not in assets:
            continue
        spec = read_json(spec_paths[board_id]) if board_id in spec_paths else {"id": board_id}
        image_path = assets[board_id].get("imagePath")
        candidates = element_candidates(spec)
        # Merge auto-prefill into candidates so the tool draws initial boxes.
        prefill_map = auto_prefill.get(board_id, {})
        for candidate in candidates:
            prefill = prefill_map.get(candidate["id"])
            if prefill:
                candidate["prefill"] = prefill
        boards.append(
            {
                "boardId": board_id,
                "title": assets[board_id].get("title") or spec.get("title") or board_id,
                "image": copy_board_image(image_path, board_id, html_dir),
                "width": assets[board_id].get("width") or spec.get("canvas", {}).get("width"),
                "height": assets[board_id].get("height") or spec.get("canvas", {}).get("height"),
                "elements": candidates,
                "existing": load_existing_calibration(calibration_dir, board_id),
                "downloadName": f"{board_id}.element_bboxes.json",
            }
        )
    return {
        "project": str(project),
        "calibrationDir": str(calibration_dir),
        "boards": boards,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>Whiteboard Calibration</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --ink: #17202a;
      --muted: #68717c;
      --line: #d6d0c4;
      --accent: #0f766e;
      --danger: #b42318;
      --amber: #c77700;
      --shadow: 0 12px 32px rgba(22, 29, 36, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .app {
      display: grid;
      grid-template-columns: 280px minmax(640px, 1fr) 360px;
      min-height: 100vh;
    }
    aside, .inspector {
      background: var(--panel);
      border-color: var(--line);
      overflow: auto;
    }
    aside { border-right: 1px solid var(--line); }
    .inspector { border-left: 1px solid var(--line); }
    header {
      padding: 18px 18px 14px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 760;
    }
    .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .board-list, .element-list { padding: 12px; display: grid; gap: 8px; }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      min-height: 36px;
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
      cursor: pointer;
    }
    button:hover { border-color: #9c9281; }
    button.active {
      border-color: var(--accent);
      background: #e7f5f2;
    }
    .board-button, .element-button {
      text-align: left;
      display: grid;
      gap: 2px;
    }
    .button-title { font-size: 13px; font-weight: 720; }
    .button-meta { font-size: 11px; color: var(--muted); }
    main {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      min-width: 0;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 253, 248, 0.86);
    }
    .toolbar .spacer { flex: 1; }
    .stage-wrap {
      min-height: 0;
      overflow: auto;
      padding: 18px;
    }
    .stage {
      position: relative;
      width: min(100%, 1180px);
      margin: 0 auto;
      background: #fff;
      box-shadow: var(--shadow);
      border: 1px solid var(--line);
    }
    #boardImage {
      display: block;
      width: 100%;
      height: auto;
      user-select: none;
      -webkit-user-drag: none;
    }
    #overlay {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      cursor: crosshair;
    }
    .section {
      padding: 14px;
      border-bottom: 1px solid var(--line);
    }
    .section-title {
      margin: 0 0 10px;
      font-size: 12px;
      font-weight: 800;
      color: #38424d;
      text-transform: uppercase;
    }
    .mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    label {
      display: grid;
      gap: 4px;
      font-size: 12px;
      color: var(--muted);
    }
    input {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
      min-width: 0;
      background: #fff;
      color: var(--ink);
    }
    .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    textarea {
      width: 100%;
      height: 300px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
      background: #111827;
      color: #f8fafc;
    }
    .status {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      background: #efe9dc;
      color: #3c372f;
      font-size: 12px;
    }
    .danger { color: var(--danger); }
    .marker-label {
      font-size: 14px;
      paint-order: stroke;
      stroke: white;
      stroke-width: 4px;
      fill: var(--ink);
      font-weight: 760;
    }
    @media (max-width: 1180px) {
      .app { grid-template-columns: 240px 1fr; }
      .inspector { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <header>
        <h1>Whiteboard Calibration</h1>
        <div class="hint">选择 board 和元素，在图片上拖框。导出的 JSON 可直接放进 calibration/。</div>
      </header>
      <div class="board-list" id="boardList"></div>
      <div class="section">
        <p class="section-title">Elements</p>
        <div class="element-list" id="elementList"></div>
      </div>
    </aside>
    <main>
      <div class="toolbar">
        <button data-mode="bbox" class="mode active">BBox</button>
        <button data-mode="target" class="mode">Target</button>
        <button data-mode="cursor" class="mode">Cursor</button>
        <button id="fitCamera">Camera From BBox</button>
        <span class="pill" id="activeInfo"></span>
        <span class="spacer"></span>
        <button id="clearElement">Clear Element</button>
      </div>
      <div class="stage-wrap">
        <div class="stage" id="stage">
          <img id="boardImage" alt="board image" />
          <svg id="overlay"></svg>
        </div>
      </div>
    </main>
    <section class="inspector">
      <div class="section">
        <p class="section-title">Selected Element</p>
        <div class="field-row">
          <label>X <input id="xInput" type="number" step="0.01"></label>
          <label>Y <input id="yInput" type="number" step="0.01"></label>
          <label>W <input id="wInput" type="number" step="0.01"></label>
          <label>H <input id="hInput" type="number" step="0.01"></label>
        </div>
        <div class="field-row" style="margin-top:8px">
          <label>Camera Scale <input id="scaleInput" type="number" min="0.6" max="2.5" step="0.01" value="1.18"></label>
          <label>Cursor Bias <input id="cursorBiasInput" type="number" step="1" value="0"></label>
        </div>
      </div>
      <div class="section">
        <p class="section-title">Export</p>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:10px;">
          <button id="downloadJson">Download JSON</button>
          <button id="copyJson">Copy JSON</button>
        </div>
        <textarea id="jsonOutput" spellcheck="false"></textarea>
        <p class="status" id="status"></p>
      </div>
    </section>
  </div>
  <script id="calibration-data" type="application/json">__CONFIG_JSON__</script>
  <script>
    const config = JSON.parse(document.getElementById('calibration-data').textContent);
    const state = { boardIndex: 0, elementId: null, mode: 'bbox', drag: null, drafts: {} };
    const $ = (id) => document.getElementById(id);
    const svg = $('overlay');
    const image = $('boardImage');
    const inputs = ['xInput', 'yInput', 'wInput', 'hInput'].map($);
    const scaleInput = $('scaleInput');
    const cursorBiasInput = $('cursorBiasInput');

    function round(n) { return Math.round(Number(n) * 100) / 100; }
    function board() { return config.boards[state.boardIndex]; }
    function draft() {
      const b = board();
      if (!state.drafts[b.boardId]) state.drafts[b.boardId] = seedDraft(b);
      return state.drafts[b.boardId];
    }
    function seedDraft(b) {
      const out = {};
      const existing = b.existing && Array.isArray(b.existing.elements) ? b.existing.elements : [];
      for (const item of existing) out[item.id] = structuredClone(item);
      // Apply auto-calibration prefill only when no manual calibration exists.
      if (Object.keys(out).length === 0) {
        for (const candidate of b.elements || []) {
          if (candidate.prefill && candidate.prefill.bbox) {
            out[candidate.id] = structuredClone(candidate.prefill);
          }
        }
      }
      return out;
    }
    function elementMeta(id) { return board().elements.find((item) => item.id === id) || { id, label: id }; }
    function elementDraft(id = state.elementId) {
      if (!id) return null;
      const d = draft();
      if (!d[id]) {
        const meta = elementMeta(id);
        d[id] = { id, text: meta.label || id, kind: meta.kind || 'element' };
        if (meta.bbox) d[id].bbox = meta.bbox;
        if (meta.annotationTargetBbox) d[id].annotationTargetBbox = meta.annotationTargetBbox;
      }
      return d[id];
    }
    function naturalSize() {
      return {
        width: image.naturalWidth || Number(board().width) || 1672,
        height: image.naturalHeight || Number(board().height) || 941,
      };
    }
    function toImagePoint(evt) {
      const rect = image.getBoundingClientRect();
      const size = naturalSize();
      return {
        x: round((evt.clientX - rect.left) * size.width / rect.width),
        y: round((evt.clientY - rect.top) * size.height / rect.height),
      };
    }
    function toSvgBox(box) {
      const rect = image.getBoundingClientRect();
      const size = naturalSize();
      return {
        x: box[0] * rect.width / size.width,
        y: box[1] * rect.height / size.height,
        w: box[2] * rect.width / size.width,
        h: box[3] * rect.height / size.height,
      };
    }
    function setMode(mode) {
      state.mode = mode;
      document.querySelectorAll('.mode').forEach((btn) => btn.classList.toggle('active', btn.dataset.mode === mode));
      render();
    }
    function selectBoard(index) {
      state.boardIndex = index;
      state.elementId = board().elements[0]?.id || null;
      image.src = board().image;
      image.onload = render;
      render();
    }
    function selectElement(id) {
      state.elementId = id;
      elementDraft();
      render();
    }
    function renderBoards() {
      $('boardList').innerHTML = config.boards.map((b, index) => `
        <button class="board-button ${index === state.boardIndex ? 'active' : ''}" data-board="${index}">
          <span class="button-title">${b.boardId}</span>
          <span class="button-meta">${b.title || ''}</span>
        </button>`).join('');
      document.querySelectorAll('[data-board]').forEach((btn) => btn.addEventListener('click', () => selectBoard(Number(btn.dataset.board))));
    }
    function renderElements() {
      $('elementList').innerHTML = board().elements.map((item) => {
        const row = draft()[item.id];
        const done = row?.bbox ? 'bbox' : 'needs box';
        return `<button class="element-button ${item.id === state.elementId ? 'active' : ''}" data-element="${item.id}">
          <span class="button-title">${item.id}</span>
          <span class="button-meta">${item.label || ''} · ${done}</span>
        </button>`;
      }).join('');
      document.querySelectorAll('[data-element]').forEach((btn) => btn.addEventListener('click', () => selectElement(btn.dataset.element)));
    }
    function drawRect(box, color, width, dash, label) {
      const r = toSvgBox(box);
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', r.x); rect.setAttribute('y', r.y); rect.setAttribute('width', r.w); rect.setAttribute('height', r.h);
      rect.setAttribute('fill', 'transparent'); rect.setAttribute('stroke', color); rect.setAttribute('stroke-width', width);
      if (dash) rect.setAttribute('stroke-dasharray', dash);
      g.appendChild(rect);
      if (label) {
        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('x', r.x + 6); t.setAttribute('y', Math.max(18, r.y - 6));
        t.setAttribute('class', 'marker-label');
        t.textContent = label;
        g.appendChild(t);
      }
      svg.appendChild(g);
    }
    function drawCursor(point) {
      const rect = image.getBoundingClientRect();
      const size = naturalSize();
      const x = point.x * rect.width / size.width;
      const y = point.y * rect.height / size.height;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.innerHTML = `<circle cx="${x}" cy="${y}" r="6" fill="#c77700" stroke="white" stroke-width="2"></circle>
        <path d="M ${x} ${y} L ${x + 18} ${y + 18}" stroke="#c77700" stroke-width="3" stroke-linecap="round"></path>`;
      svg.appendChild(g);
    }
    function updateInputs() {
      const row = elementDraft();
      const box = row?.bbox || [0, 0, 0, 0];
      inputs.forEach((input, index) => input.value = box[index] ?? 0);
      scaleInput.value = row?.camera?.scale ?? scaleInput.value ?? 1.18;
      $('activeInfo').textContent = `${board().boardId} / ${state.elementId || 'no element'} / ${state.mode}`;
    }
    function exportJson() {
      const size = naturalSize();
      const rows = Object.values(draft()).filter((item) => Array.isArray(item.bbox));
      const data = {
        boardId: board().boardId,
        canvas: { width: size.width, height: size.height },
        elements: rows.map((item) => {
          const box = item.bbox.map(round);
          const target = (item.annotationTargetBbox || item.bbox).map(round);
          const cx = round(box[0] + box[2] / 2);
          const cy = round(box[1] + box[3] / 2);
          const exported = {
            id: item.id,
            text: item.text || elementMeta(item.id).label || item.id,
            kind: item.kind || elementMeta(item.id).kind || 'element',
            bbox: box,
            annotationTargetBbox: target,
            camera: item.camera || { x: cx, y: cy, scale: Number(scaleInput.value || 1.18) },
          };
          if (item.cursor) exported.cursor = { x: round(item.cursor.x), y: round(item.cursor.y) };
          return exported;
        }),
      };
      return JSON.stringify(data, null, 2);
    }
    function renderJson() {
      $('jsonOutput').value = exportJson();
      $('status').textContent = `保存为 ${board().downloadName}，放到 ${config.calibrationDir}`;
    }
    function renderOverlay() {
      const rect = image.getBoundingClientRect();
      svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
      svg.innerHTML = '';
      for (const item of Object.values(draft())) {
        if (item.bbox) drawRect(item.bbox, item.id === state.elementId ? '#0f766e' : '#64748b', item.id === state.elementId ? 3 : 1.5, '', item.id);
        if (item.annotationTargetBbox) drawRect(item.annotationTargetBbox, '#b42318', 2, '7 5', '');
        if (item.cursor) drawCursor(item.cursor);
      }
    }
    function render() {
      renderBoards();
      renderElements();
      updateInputs();
      renderOverlay();
      renderJson();
    }
    function setBoxFromInputs() {
      const row = elementDraft();
      row.bbox = inputs.map((input) => round(input.value));
      fitCamera(row);
      render();
    }
    function fitCamera(row = elementDraft()) {
      if (!row?.bbox) return;
      const [x, y, w, h] = row.bbox;
      row.camera = { x: round(x + w / 2), y: round(y + h / 2), scale: Number(scaleInput.value || 1.18) };
      if (!row.cursor) row.cursor = { x: round(x + w * 0.82), y: round(y + h * 0.5 + Number(cursorBiasInput.value || 0)) };
    }
    svg.addEventListener('pointerdown', (evt) => {
      if (!state.elementId) return;
      const p = toImagePoint(evt);
      if (state.mode === 'cursor') {
        const row = elementDraft();
        row.cursor = p;
        render();
        return;
      }
      state.drag = { start: p, current: p };
      svg.setPointerCapture(evt.pointerId);
    });
    svg.addEventListener('pointermove', (evt) => {
      if (!state.drag) return;
      state.drag.current = toImagePoint(evt);
      const row = elementDraft();
      const a = state.drag.start;
      const b = state.drag.current;
      const box = [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y)].map(round);
      if (state.mode === 'target') row.annotationTargetBbox = box;
      else {
        row.bbox = box;
        if (!row.annotationTargetBbox) row.annotationTargetBbox = box;
        fitCamera(row);
      }
      render();
    });
    svg.addEventListener('pointerup', () => { state.drag = null; });
    document.querySelectorAll('.mode').forEach((btn) => btn.addEventListener('click', () => setMode(btn.dataset.mode)));
    inputs.forEach((input) => input.addEventListener('change', setBoxFromInputs));
    scaleInput.addEventListener('change', () => { fitCamera(); render(); });
    cursorBiasInput.addEventListener('change', () => { fitCamera(); render(); });
    $('fitCamera').addEventListener('click', () => { fitCamera(); render(); });
    $('clearElement').addEventListener('click', () => {
      if (!state.elementId) return;
      delete draft()[state.elementId];
      render();
    });
    $('downloadJson').addEventListener('click', () => {
      const blob = new Blob([exportJson() + '\\n'], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = board().downloadName;
      a.click();
      URL.revokeObjectURL(a.href);
    });
    $('copyJson').addEventListener('click', async () => {
      await navigator.clipboard.writeText(exportJson());
      $('status').textContent = 'JSON copied';
    });
    window.addEventListener('resize', renderOverlay);
    selectBoard(0);
  </script>
</body>
</html>
"""


def write_tool(config: dict[str, Any], output_dir: Path, overwrite: bool) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "index.html"
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} already exists; pass --overwrite to replace it")
    html = HTML_TEMPLATE.replace("__CONFIG_JSON__", json.dumps(config, ensure_ascii=False))
    out.write_text(html, encoding="utf-8")
    readme = output_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Calibration Tool",
                "",
                "Open `index.html` in a browser.",
                "",
                "Workflow:",
                "",
                "1. Select a board.",
                "2. Select an element.",
                "3. Drag `BBox` around the whole visual object.",
                "4. Drag `Target` around the exact text or area to annotate.",
                "5. Click `Cursor` where the mouse should land.",
                "6. Download `<boardId>.element_bboxes.json` and place it in the calibration directory.",
                "",
                f"Calibration directory: `{config.get('calibrationDir')}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a browser calibration tool for D board bbox handoff.")
    parser.add_argument("--project", required=True, type=Path, help="Project root containing board_asset_manifest.json and infographic/.")
    parser.add_argument("--asset-manifest", type=Path, help="Defaults to <project>/board_asset_manifest.json")
    parser.add_argument("--infographic-plan", type=Path, help="Defaults to <project>/infographic/infographic_plan.json")
    parser.add_argument("--calibration-dir", type=Path, help="Defaults to <project>/calibration")
    parser.add_argument("--output-dir", type=Path, help="Defaults to <project>/calibration_tool")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite index.html if it already exists.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result.")
    parser.add_argument(
        "--prefill-from",
        type=Path,
        help="Path to auto_calibration_report.json; prefill detected bboxes into the tool.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    asset_manifest = (args.asset_manifest or project / "board_asset_manifest.json").resolve()
    infographic_plan = (args.infographic_plan or project / "infographic" / "infographic_plan.json").resolve()
    calibration_dir = (args.calibration_dir or project / "calibration").resolve()
    output_dir = (args.output_dir or project / "calibration_tool").resolve()

    if not asset_manifest.exists():
        raise FileNotFoundError(f"asset manifest not found: {asset_manifest}")
    if not infographic_plan.exists():
        raise FileNotFoundError(f"infographic plan not found: {infographic_plan}")

    config = build_config(project, asset_manifest, infographic_plan, calibration_dir, output_dir, args.prefill_from)
    if not config["boards"]:
        raise ValueError("no boards found for calibration tool")
    index = write_tool(config, output_dir, args.overwrite)
    result = {
        "status": "PASS",
        "index": str(index),
        "boards": [board["boardId"] for board in config["boards"]],
        "calibrationDir": str(calibration_dir),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] calibration tool written: {index}")
        print(f"boards: {', '.join(result['boards'])}")
        print(f"calibrationDir: {calibration_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
