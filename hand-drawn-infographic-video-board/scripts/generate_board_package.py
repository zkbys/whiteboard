#!/usr/bin/env python3
"""Generate a video-ready hand-drawn infographic board package.

The script creates a deterministic control layer for a board PNG. It does not
try to reconstruct a raster image. If the PNG is already hand-generated, pass
explicit element bboxes in board_spec.json or run a calibration pass before
rendering the final video.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_W = 1920
BASE_H = 1080

PALETTE = {
    "paper": "#faf8f3",
    "ink": "#1a2332",
    "teal": "#4a9d9e",
    "teal_dark": "#1f7a7a",
    "blue": "#2d5a7b",
    "amber": "#f4a261",
    "red": "#d8232a",
    "shadow": "#e8dcc8",
}

SUPPORTED_ANNOTATIONS = ("underline", "circle", "box", "check", "strike")
ANNOTATION_ALIASES = {
    "highlight": "underline",
    "point": "underline",
    "zoom": "box",
    "frame": "box",
    "rect": "box",
}
DEFAULT_ACTION_DURATION = {
    "underline": 0.72,
    "circle": 0.95,
    "box": 0.82,
    "check": 0.6,
    "strike": 0.58,
}


@dataclass(frozen=True)
class Canvas:
    width: int
    height: int

    @property
    def sx(self) -> float:
        return self.width / BASE_W

    @property
    def sy(self) -> float:
        return self.height / BASE_H

    def xy(self, x: float, y: float) -> list[float]:
        return [round(x * self.sx, 2), round(y * self.sy, 2)]

    def box(self, x: float, y: float, w: float, h: float) -> list[float]:
        return [round(x * self.sx, 2), round(y * self.sy, 2), round(w * self.sx, 2), round(h * self.sy, 2)]


def slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "item"


def ensure_id(value: str, fallback: str) -> str:
    raw = value or fallback
    ident = slug(raw)
    # Keep generated IDs selector-friendly. Chinese labels are readable but
    # awkward as element ids, so generated item ids use stable fallbacks.
    if re.search(r"[\u4e00-\u9fff]", ident):
        return slug(fallback)
    return ident


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_spec(path: Path) -> dict[str, Any]:
    spec = read_json(path)
    if not isinstance(spec, dict):
        raise ValueError("board_spec.json must be a JSON object")
    if not spec.get("title"):
        raise ValueError("board_spec.json requires a title")
    if not spec.get("sections") and not spec.get("elements") and not spec.get("keyObjects"):
        raise ValueError("board_spec.json requires sections, elements, or keyObjects")
    return spec


def calibration_candidates(calibration_dir: Path, board_id: str) -> list[Path]:
    return [
        calibration_dir / f"{board_id}.element_bboxes.json",
        calibration_dir / f"{board_id}.calibration.json",
        calibration_dir / board_id / "element_bboxes.json",
        calibration_dir / board_id / "calibration.json",
    ]


def load_calibration(calibration_dir: Path | None, board_id: str | None) -> tuple[dict[str, Any] | None, Path | None]:
    if not calibration_dir or not board_id:
        return None, None
    for candidate in calibration_candidates(calibration_dir, board_id):
        if candidate.exists():
            data = read_json(candidate)
            if not isinstance(data, dict):
                raise ValueError(f"calibration file must be a JSON object: {candidate}")
            return data, candidate
    return None, None


def calibration_elements(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("elements") or data.get("bboxes") or []
    if isinstance(raw, dict):
        items = []
        for element_id, value in raw.items():
            item = dict(value) if isinstance(value, dict) else {"bbox": value}
            item["id"] = item.get("id") or element_id
            items.append(item)
        return items
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def spec_element_defaults(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults: dict[str, dict[str, Any]] = {}
    defaults["title"] = {
        "id": "title",
        "kind": "title",
        "role": "title",
        "text": spec.get("title", "title"),
        "actions": ["circle", "underline"],
    }
    for raw in spec.get("elements", []) or []:
        if raw.get("id"):
            defaults[str(raw["id"])] = dict(raw)
    for raw in spec.get("keyObjects", []) or []:
        if raw.get("id"):
            defaults[str(raw["id"])] = {
                "id": raw.get("id"),
                "kind": raw.get("role", "element"),
                "role": raw.get("role"),
                "text": raw.get("label") or raw.get("text") or raw.get("id"),
                "actions": raw.get("actions") or actions_for_role(raw.get("role")),
            }
    return defaults


def apply_calibration(
    spec: dict[str, Any],
    calibration: dict[str, Any] | None,
    calibration_path: Path | None,
    warnings: list[str],
) -> dict[str, Any]:
    if not calibration:
        return spec
    calibrated = copy.deepcopy(spec)
    defaults = spec_element_defaults(spec)
    merged_elements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in calibration_elements(calibration):
        element_id = item.get("id")
        if not element_id:
            warnings.append(f"calibration item without id ignored in {calibration_path}")
            continue
        if not item.get("bbox"):
            warnings.append(f"calibration item {element_id} without bbox ignored in {calibration_path}")
            continue
        base = copy.deepcopy(defaults.get(str(element_id), {"id": element_id, "kind": "element", "text": element_id}))
        base.update(item)
        base["id"] = str(element_id)
        if not base.get("text"):
            base["text"] = base.get("label") or base["id"]
        if not base.get("kind"):
            base["kind"] = base.get("role", "element")
        if not base.get("actions") and not base.get("annotationTypes") and not base.get("annotations"):
            base["actions"] = actions_for_role(base.get("role"))
        merged_elements.append(base)
        seen.add(str(element_id))

    if not merged_elements:
        warnings.append(f"calibration file had no usable elements: {calibration_path}")
        return spec

    if isinstance(calibration.get("canvas"), dict):
        calibrated["canvas"] = calibration["canvas"]
    calibrated["elements"] = merged_elements
    calibrated["calibrationSource"] = str(calibration_path) if calibration_path else "inline-calibration"
    warnings.append(f"applied calibration file: {calibration_path}")
    missing_targets = [
        str(item.get("id"))
        for item in spec.get("keyObjects", []) or []
        if item.get("id") and str(item.get("id")) not in seen
    ]
    if missing_targets:
        warnings.append(
            "calibration did not include all keyObjects; only calibrated elements are exposed to D control layer: "
            + ", ".join(missing_targets)
        )
    return calibrated


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a valid PNG")
    return struct.unpack(">II", header[16:24])


def canvas_from_inputs(spec: dict[str, Any], board_image: Path | None) -> tuple[Canvas, list[str]]:
    warnings: list[str] = []
    spec_canvas = spec.get("canvas") or {}
    spec_w = int(spec_canvas.get("width", 0) or 0)
    spec_h = int(spec_canvas.get("height", 0) or 0)

    if board_image:
        img_w, img_h = png_size(board_image)
        if spec_w and spec_h and (spec_w, spec_h) != (img_w, img_h):
            warnings.append(
                f"board_spec canvas {spec_w}x{spec_h} differs from board.png {img_w}x{img_h}; "
                "using board.png pixels as the control coordinate system."
            )
        return Canvas(img_w, img_h), warnings
    if spec_w and spec_h:
        return Canvas(spec_w, spec_h), warnings
    return Canvas(BASE_W, BASE_H), warnings


def normalize_annotation_type(value: str | None) -> str:
    normalized = (value or "underline").strip().lower()
    normalized = ANNOTATION_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_ANNOTATIONS:
        raise ValueError(
            f"Unsupported annotation type '{value}'. Supported: {', '.join(SUPPORTED_ANNOTATIONS)}"
        )
    return normalized


def normalize_actions(actions: list[str] | None, fallback: str = "underline") -> list[str]:
    values = actions or [fallback]
    normalized: list[str] = []
    for value in values:
        action_type = normalize_annotation_type(str(value))
        if action_type not in normalized:
            normalized.append(action_type)
    return normalized


def point(value: list[float]) -> list[float]:
    return [round(float(value[0]), 2), round(float(value[1]), 2)]


def bbox(value: list[float]) -> list[float]:
    if len(value) != 4:
        raise ValueError(f"bbox must be [x, y, width, height], got {value}")
    x, y, w, h = [float(v) for v in value]
    if w <= 0 or h <= 0:
        raise ValueError(f"bbox width and height must be positive, got {value}")
    return [round(x, 2), round(y, 2), round(w, 2), round(h, 2)]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_point(value: list[float], canvas: Canvas) -> list[float]:
    return [
        round(clamp(float(value[0]), 0, canvas.width), 2),
        round(clamp(float(value[1]), 0, canvas.height), 2),
    ]


def camera_for_bbox(bounds: list[float], canvas: Canvas, requested_scale: float | None = None) -> dict[str, float]:
    x, y, w, h = bounds
    if requested_scale is None:
        fit_w = 1920 / max(w * 2.15, 1)
        fit_h = 1080 / max(h * 2.15, 1)
        requested_scale = min(1.7, max(0.55, min(fit_w, fit_h)))
    return {"x": round(x + w / 2, 2), "y": round(y + h / 2, 2), "scale": round(requested_scale, 3)}


def cursor_for_bbox(bounds: list[float], canvas: Canvas) -> dict[str, float]:
    x, y, w, h = bounds
    cx = x + w * 0.82
    cy = y + h * 0.58
    px, py = clamp_point([cx, cy], canvas)
    return {"x": px, "y": py}


def inset_bbox(bounds: list[float], pct_x: float = 0.08, pct_y: float = 0.18) -> list[float]:
    x, y, w, h = bounds
    dx = min(w * pct_x, w * 0.22)
    dy = min(h * pct_y, h * 0.32)
    return bbox([x + dx, y + dy, max(1, w - 2 * dx), max(1, h - 2 * dy)])


def annotation_geometry(
    annotation_type: str,
    target_bounds: list[float],
    canvas: Canvas,
    annotation_id: str,
) -> dict[str, Any]:
    x, y, w, h = target_bounds
    pad_x = max(8 * canvas.sx, min(w * 0.08, 36 * canvas.sx))
    pad_y = max(7 * canvas.sy, min(h * 0.16, 24 * canvas.sy))
    data: dict[str, Any] = {
        "type": annotation_type,
        "targetTextBbox": bbox(target_bounds),
    }

    if annotation_type == "underline":
        y_line = y + h * 0.86
        start = clamp_point([x + pad_x, y_line], canvas)
        end = clamp_point([x + w - pad_x, y_line - 2 * canvas.sy], canvas)
        data.update(
            {
                "underlineStart": start,
                "underlineEnd": end,
                "controlPoints": [
                    clamp_point([x + w * 0.28, y_line + h * 0.12], canvas),
                    clamp_point([x + w * 0.56, y_line - h * 0.08], canvas),
                    clamp_point([x + w * 0.82, y_line + h * 0.05], canvas),
                ],
                "cursorStart": clamp_point([start[0], start[1] - 15 * canvas.sy], canvas),
                "cursorEnd": clamp_point([end[0], end[1] - 15 * canvas.sy], canvas),
            }
        )
    elif annotation_type == "circle":
        center = clamp_point([x + w / 2, y + h / 2], canvas)
        data.update(
            {
                "circleCenter": center,
                "radius": [round(w * 0.58, 2), round(h * 0.68, 2)],
                "cursorStart": clamp_point([center[0], center[1] - h * 0.84], canvas),
                "cursorEnd": clamp_point([x + w * 0.96, y + h * 0.7], canvas),
            }
        )
    elif annotation_type == "box":
        box_bounds = bbox(
            [
                clamp(x - pad_x, 0, canvas.width),
                clamp(y - pad_y, 0, canvas.height),
                min(w + pad_x * 2, canvas.width - max(0, x - pad_x)),
                min(h + pad_y * 2, canvas.height - max(0, y - pad_y)),
            ]
        )
        data.update(
            {
                "boxBounds": box_bounds,
                "cornerRadius": round(min(28 * canvas.sx, 28 * canvas.sy, h * 0.26), 2),
                "cursorStart": clamp_point([box_bounds[0], box_bounds[1]], canvas),
                "cursorEnd": clamp_point([box_bounds[0] + box_bounds[2], box_bounds[1] + box_bounds[3] * 0.72], canvas),
            }
        )
    elif annotation_type == "check":
        pts = [
            clamp_point([x + w * 0.16, y + h * 0.58], canvas),
            clamp_point([x + w * 0.34, y + h * 0.78], canvas),
            clamp_point([x + w * 0.76, y + h * 0.22], canvas),
        ]
        data.update(
            {
                "points": pts,
                "cursorStart": clamp_point([pts[0][0], pts[0][1] - 15 * canvas.sy], canvas),
                "cursorEnd": clamp_point([pts[-1][0], pts[-1][1] - 15 * canvas.sy], canvas),
            }
        )
    elif annotation_type == "strike":
        y_line = y + h * 0.52
        start = clamp_point([x + pad_x, y_line], canvas)
        end = clamp_point([x + w - pad_x, y_line - 3 * canvas.sy], canvas)
        data.update(
            {
                "strikeStart": start,
                "strikeEnd": end,
                "controlPoints": [
                    clamp_point([x + w * 0.28, y_line - h * 0.15], canvas),
                    clamp_point([x + w * 0.58, y_line + h * 0.12], canvas),
                    clamp_point([x + w * 0.84, y_line - h * 0.08], canvas),
                ],
                "cursorStart": clamp_point([start[0], start[1] - 15 * canvas.sy], canvas),
                "cursorEnd": clamp_point([end[0], end[1] - 15 * canvas.sy], canvas),
            }
        )
    data["id"] = annotation_id
    return data


def make_annotation_id(annotation_type: str, element_id: str, existing: set[str]) -> str:
    base = f"{annotation_type}_{element_id}"
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}_{index}"
        index += 1
    existing.add(candidate)
    return candidate


def add_annotations_to_element(
    element: dict[str, Any],
    actions: list[str],
    canvas: Canvas,
    existing_ids: set[str],
) -> None:
    annotations = element.setdefault("annotations", {})
    target_bounds = bbox(element.get("annotationTargetBbox") or element["bbox"])
    for action_type in normalize_actions(actions):
        if any(item.get("type") == action_type for item in annotations.values()):
            continue
        annotation_id = make_annotation_id(action_type, element["id"], existing_ids)
        annotations[annotation_id] = annotation_geometry(action_type, target_bounds, canvas, annotation_id)
    element["actions"] = sorted({item["type"] for item in annotations.values()})


def text(x: float, y: float, value: str, cls: str, anchor: str = "middle") -> str:
    return (
        f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">'
        f"{html.escape(value)}</text>"
    )


def path(d: str, cls: str = "ink") -> str:
    return f'<path class="{cls}" d="{d}" />'


def rect(x: float, y: float, w: float, h: float, cls: str = "box", rx: float = 12) -> str:
    return f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" />'


def wrap_text(value: str, max_chars: int) -> list[str]:
    if len(value) <= max_chars:
        return [value]
    return [value[i : i + max_chars] for i in range(0, len(value), max_chars)]


def add_element(
    elements: list[dict[str, Any]],
    element_id: str,
    kind: str,
    label: str,
    bounds: list[float],
    actions: list[str] | None,
    canvas: Canvas,
    scale: float | None = None,
    annotation_bounds: list[float] | None = None,
    existing_annotation_ids: set[str] | None = None,
) -> dict[str, Any]:
    clean_bbox = bbox(bounds)
    element = {
        "id": element_id,
        "kind": kind,
        "text": label,
        "bbox": clean_bbox,
        "camera": camera_for_bbox(clean_bbox, canvas, scale),
        "cursor": cursor_for_bbox(clean_bbox, canvas),
    }
    if annotation_bounds:
        element["annotationTargetBbox"] = bbox(annotation_bounds)
    add_annotations_to_element(element, actions or ["underline"], canvas, existing_annotation_ids or set())
    elements.append(element)
    return element


def explicit_elements(spec: dict[str, Any], canvas: Canvas, existing_annotation_ids: set[str]) -> list[dict[str, Any]]:
    raw_items = spec.get("elements") or []
    elements: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        element_id = ensure_id(raw.get("id", ""), f"element-{index + 1}")
        raw_bbox = raw.get("bbox")
        if not raw_bbox:
            raise ValueError(f"Explicit element '{element_id}' requires bbox")
        actions = raw.get("actions") or raw.get("annotationTypes") or [raw.get("effect", "underline")]
        element = add_element(
            elements,
            element_id,
            raw.get("kind", raw.get("role", "element")),
            raw.get("text") or raw.get("label") or element_id,
            bbox(raw_bbox),
            actions,
            canvas,
            raw.get("camera", {}).get("scale") if isinstance(raw.get("camera"), dict) else None,
            raw.get("annotationTargetBbox") or raw.get("targetTextBbox"),
            existing_annotation_ids,
        )
        if isinstance(raw.get("camera"), dict):
            element["camera"] = raw["camera"]
        if isinstance(raw.get("cursor"), dict):
            element["cursor"] = raw["cursor"]
        if isinstance(raw.get("annotations"), dict):
            element["annotations"] = raw["annotations"]
            for annotation_id in raw["annotations"]:
                existing_annotation_ids.add(annotation_id)
            element["actions"] = sorted({item["type"] for item in raw["annotations"].values()})
    return elements


def has_explicit_elements(spec: dict[str, Any]) -> bool:
    return bool(spec.get("elements")) and all(item.get("bbox") for item in spec.get("elements", []))


def actions_for_role(role: str | None) -> list[str]:
    role_value = (role or "").lower()
    if role_value in {"problem", "alternative"}:
        return ["box", "underline", "strike"]
    if role_value in {"standard", "takeaway"}:
        return ["check", "box", "underline"]
    if role_value in {"mechanism"}:
        return ["underline", "circle", "box"]
    return ["underline", "circle", "box"]


def build_key_object_layout(
    spec: dict[str, Any],
    canvas: Canvas,
    existing_annotation_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    key_objects = spec.get("keyObjects") or []
    elements: list[dict[str, Any]] = []
    parts: list[str] = []
    count = max(1, len(key_objects))
    cols = min(3, count)
    rows = (count + cols - 1) // cols
    margin_x = canvas.width * 0.11
    gap_x = canvas.width * 0.06
    card_w = (canvas.width - 2 * margin_x - gap_x * (cols - 1)) / cols
    card_h = min(canvas.height * 0.18, max(canvas.height * 0.12, canvas.height * 0.42 / max(1, rows)))
    top = canvas.height * 0.34
    gap_y = canvas.height * 0.08

    for index, raw in enumerate(key_objects):
        row = index // cols
        col = index % cols
        element_id = ensure_id(raw.get("id", ""), f"key-object-{index + 1}")
        x = margin_x + col * (card_w + gap_x)
        y = top + row * (card_h + gap_y)
        raw_bbox = raw.get("bbox")
        bounds = bbox(raw_bbox) if raw_bbox else bbox([x, y, card_w, card_h])
        label = raw.get("label") or raw.get("text") or element_id
        element = add_element(
            elements,
            element_id,
            raw.get("role", "key_object"),
            label,
            bounds,
            raw.get("actions") or actions_for_role(raw.get("role")),
            canvas,
            None,
            raw.get("annotationTargetBbox") or raw.get("targetTextBbox") or inset_bbox(bounds, 0.08, 0.18),
            existing_annotation_ids,
        )
        element["sourceKeyObject"] = {
            "role": raw.get("role"),
            "visualForm": raw.get("visualForm"),
            "sourceSegments": raw.get("sourceSegments", []),
        }

        parts.append(f'<g id="element-{element_id}" data-kind="key-object">')
        parts.append(rect(bounds[0], bounds[1], bounds[2], bounds[3], "box", 18 * canvas.sx))
        parts.append(text(bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] * 0.5, label, "label"))
        if raw.get("role"):
            parts.append(text(bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] * 0.78, str(raw["role"]), "note"))
        parts.append(rect(*bounds, "target", 0))
        parts.append("</g>")

    relationships = spec.get("relationships") or []
    element_boxes = {item["id"]: item["bbox"] for item in elements}
    for rel in relationships:
        source = element_boxes.get(rel.get("from"))
        target = element_boxes.get(rel.get("to"))
        if not source or not target:
            continue
        sx = source[0] + source[2]
        sy = source[1] + source[3] / 2
        tx = target[0]
        ty = target[1] + target[3] / 2
        parts.append(
            f'<path class="ink teal" d="M {sx:.1f} {sy:.1f} C {(sx+tx)/2:.1f} {sy:.1f}, {(sx+tx)/2:.1f} {ty:.1f}, {tx:.1f} {ty:.1f}" marker-end="url(#arrow)" />'
        )

    return elements, parts


def section_layout(spec: dict[str, Any], canvas: Canvas) -> list[dict[str, Any]]:
    sections = spec.get("sections", [])
    cols = max(1, min(4, len(sections)))
    margin = canvas.width * 0.095
    gap = canvas.width * 0.045
    col_w = (canvas.width - margin * 2 - gap * (cols - 1)) / cols
    top = canvas.height * 0.29
    base_h = canvas.height * 0.52

    layouts: list[dict[str, Any]] = []
    for i, section in enumerate(sections[:cols]):
        x = margin + i * (col_w + gap)
        w = col_w
        h = base_h * (1.08 if cols >= 3 and i == 1 else 1.0)
        y = top - (canvas.height * 0.02 if cols >= 3 and i == 1 else 0)
        layouts.append({"section": section, "index": i, "x": x, "y": y, "w": w, "h": h, "items": section.get("items", [])})
    return layouts


def build_svg_and_manifest(
    spec: dict[str, Any],
    canvas: Canvas,
    source_image: str | None,
    warnings: list[str],
    asset_ref: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    parts: list[str] = []
    elements: list[dict[str, Any]] = []
    existing_annotation_ids: set[str] = set()

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas.width} {canvas.height}" width="{canvas.width}" height="{canvas.height}">'
    )
    parts.append(
        f"""
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="8" markerHeight="8" orient="auto">
    <path d="M0,0 L10,5 L0,10 Z" fill="{PALETTE["teal_dark"]}" />
  </marker>
  <filter id="roughen">
    <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="2" seed="7" />
    <feDisplacementMap in="SourceGraphic" scale="{max(0.8, canvas.sx * 1.2):.2f}" />
  </filter>
</defs>
<style>
  .paper {{ fill: {PALETTE["paper"]}; }}
  .grid {{ stroke: rgba(26,35,50,0.045); stroke-width: {max(1, canvas.sx):.2f}; }}
  .ink {{ stroke: {PALETTE["ink"]}; stroke-width: {4 * canvas.sx:.2f}; fill: none; stroke-linecap: round; stroke-linejoin: round; filter: url(#roughen); }}
  .thin {{ stroke: {PALETTE["ink"]}; stroke-width: {2.4 * canvas.sx:.2f}; fill: none; stroke-linecap: round; stroke-linejoin: round; filter: url(#roughen); }}
  .teal {{ stroke: {PALETTE["teal_dark"]}; }}
  .blue {{ stroke: {PALETTE["blue"]}; }}
  .amber {{ stroke: {PALETTE["amber"]}; }}
  .box {{ fill: rgba(255,255,255,0.42); stroke: {PALETTE["ink"]}; stroke-width: {3 * canvas.sx:.2f}; filter: url(#roughen); }}
  .machine {{ fill: rgba(255,255,255,0.35); stroke: {PALETTE["teal_dark"]}; stroke-width: {4 * canvas.sx:.2f}; filter: url(#roughen); }}
  .title {{ font: 700 {64 * canvas.sy:.1f}px "Kaiti SC", "STKaiti", "KaiTi", sans-serif; fill: {PALETTE["ink"]}; }}
  .subtitle {{ font: 500 {26 * canvas.sy:.1f}px "Kaiti SC", "STKaiti", "KaiTi", sans-serif; fill: {PALETTE["blue"]}; }}
  .section {{ font: 700 {38 * canvas.sy:.1f}px "Kaiti SC", "STKaiti", "KaiTi", sans-serif; fill: {PALETTE["ink"]}; }}
  .label {{ font: 650 {30 * canvas.sy:.1f}px "Kaiti SC", "STKaiti", "KaiTi", sans-serif; fill: {PALETTE["ink"]}; }}
  .note {{ font: 650 {25 * canvas.sy:.1f}px "Kaiti SC", "STKaiti", "KaiTi", sans-serif; fill: {PALETTE["blue"]}; }}
  .num {{ font: 500 {28 * canvas.sy:.1f}px Menlo, monospace; fill: {PALETTE["teal_dark"]}; }}
  .target {{ fill: transparent; stroke: rgba(244,162,97,0.001); }}
</style>
"""
    )
    parts.append(rect(0, 0, canvas.width, canvas.height, "paper", 0))
    grid_gap = max(48, round(64 * canvas.sx))
    for x in range(0, canvas.width + 1, grid_gap):
        parts.append(f'<line class="grid" x1="{x}" y1="0" x2="{x}" y2="{canvas.height}" />')
    for y in range(0, canvas.height + 1, grid_gap):
        parts.append(f'<line class="grid" x1="0" y1="{y}" x2="{canvas.width}" y2="{y}" />')

    title_bounds = [canvas.width * 0.18, canvas.height * 0.055, canvas.width * 0.64, canvas.height * 0.095]
    title_annotation_bounds = inset_bbox(title_bounds, 0.04, 0.1)
    explicit_title = any(str(item.get("id")) == "title" and item.get("bbox") for item in spec.get("elements", []) or [])
    if not explicit_title:
        add_element(
            elements,
            "title",
            "title",
            spec["title"],
            title_bounds,
            ["circle", "underline"],
            canvas,
            1.08,
            title_annotation_bounds,
            existing_annotation_ids,
        )
    parts.append('<g id="element-title" data-kind="title">')
    parts.append(text(canvas.width / 2, canvas.height * 0.11, spec["title"], "title"))
    if spec.get("subtitle"):
        parts.append(text(canvas.width / 2, canvas.height * 0.15, spec["subtitle"], "subtitle"))
    parts.append(
        path(
            f"M {canvas.width * 0.22:.1f} {canvas.height * 0.165:.1f} C {canvas.width * 0.37:.1f} {canvas.height * 0.178:.1f}, {canvas.width * 0.64:.1f} {canvas.height * 0.178:.1f}, {canvas.width * 0.78:.1f} {canvas.height * 0.163:.1f}",
            "ink",
        )
    )
    parts.append(rect(*title_bounds, "target", 0))
    parts.append("</g>")

    if has_explicit_elements(spec):
        elements.extend(explicit_elements(spec, canvas, existing_annotation_ids))
    elif spec.get("keyObjects"):
        key_elements, key_parts = build_key_object_layout(spec, canvas, existing_annotation_ids)
        elements.extend(key_elements)
        parts.extend(key_parts)
    else:
        layouts = section_layout(spec, canvas)
        for layout in layouts:
            section = layout["section"]
            sec_id = ensure_id(section.get("id", ""), f"section-{layout['index'] + 1}")
            x, y, w, h = layout["x"], layout["y"], layout["w"], layout["h"]
            section_title_bounds = [x + w * 0.08, y - canvas.height * 0.075, w * 0.84, canvas.height * 0.065]
            sec_bounds = [x - canvas.width * 0.018, y - canvas.height * 0.09, w + canvas.width * 0.036, h + canvas.height * 0.12]
            add_element(
                elements,
                sec_id,
                "section",
                section["title"],
                sec_bounds,
                section.get("actions", ["underline"]),
                canvas,
                1.24,
                section_title_bounds,
                existing_annotation_ids,
            )

            parts.append(f'<g id="element-{sec_id}" data-kind="section">')
            parts.append(text(x + w / 2, y - canvas.height * 0.044, section["title"], "section"))
            parts.append(path(f"M {x + w * 0.1:.1f} {y - canvas.height * 0.023:.1f} C {x + w * 0.35:.1f} {y - canvas.height * 0.014:.1f}, {x + w * 0.65:.1f} {y - canvas.height * 0.014:.1f}, {x + w * 0.9:.1f} {y - canvas.height * 0.024:.1f}", "thin"))
            if layout["index"] == 1 and len(layouts) >= 3:
                parts.append(rect(x, y, w, h, "machine", 34 * canvas.sx))
            else:
                parts.append(path(f"M {x:.1f} {y:.1f} L {x + w - 18 * canvas.sx:.1f} {y:.1f} L {x + w:.1f} {y + 22 * canvas.sy:.1f} L {x + w:.1f} {y + h:.1f} L {x:.1f} {y + h:.1f} Z", "ink"))

            item_count = max(1, len(layout["items"]))
            item_y = y + h * 0.16
            item_gap = min(canvas.height * 0.11, max(canvas.height * 0.075, (h - canvas.height * 0.14) / item_count))
            for item_i, item in enumerate(layout["items"]):
                item_id = ensure_id("", f"{sec_id}-item-{item_i + 1}")
                item_bounds = [x + w * 0.1, item_y - canvas.height * 0.04, w * 0.8, canvas.height * 0.065]
                item_annotation_bounds = inset_bbox(item_bounds, 0.06, 0.12)
                add_element(
                    elements,
                    item_id,
                    "item",
                    item,
                    item_bounds,
                    section.get("actions", ["underline"]),
                    canvas,
                    1.5,
                    item_annotation_bounds,
                    existing_annotation_ids,
                )
                parts.append(f'<g id="element-{item_id}" data-kind="item">')
                if layout["index"] == 1 and len(layouts) >= 3:
                    parts.append(rect(item_bounds[0], item_bounds[1], item_bounds[2], item_bounds[3], "box", 14 * canvas.sx))
                    parts.append(f'<circle class="thin teal" cx="{x + w * 0.19:.1f}" cy="{item_y - canvas.height * 0.008:.1f}" r="{25 * canvas.sx:.1f}" />')
                    parts.append(text(x + w * 0.19, item_y + canvas.height * 0.002, str(item_i + 1), "num"))
                    parts.append(text(x + w * 0.33, item_y + canvas.height * 0.002, item, "label", "start"))
                else:
                    parts.append(rect(item_bounds[0], item_bounds[1], item_bounds[2], item_bounds[3], "box", 8 * canvas.sx))
                    parts.append(text(x + w / 2, item_y + canvas.height * 0.002, item, "label"))
                parts.append(rect(*item_bounds, "target", 0))
                parts.append("</g>")
                item_y += item_gap

            parts.append(rect(*sec_bounds, "target", 0))
            parts.append("</g>")

        for left, right in zip(layouts, layouts[1:]):
            x1 = left["x"] + left["w"] + canvas.width * 0.025
            y1 = left["y"] + left["h"] * 0.48
            x2 = right["x"] - canvas.width * 0.03
            parts.append(
                f'<path class="ink teal" d="M {x1:.1f} {y1:.1f} C {(x1+x2)/2:.1f} {y1:.1f}, {(x1+x2)/2:.1f} {y1:.1f}, {x2:.1f} {y1:.1f}" marker-end="url(#arrow)" />'
            )

        notes = spec.get("notes", [])
        for note_i, note in enumerate(notes):
            target_section = note.get("target_section")
            target_layout = next((l for l in layouts if l["section"].get("id") == target_section), layouts[min(1, len(layouts) - 1)])
            note_id = ensure_id(note.get("id", ""), f"note-{note_i + 1}")
            nx = target_layout["x"] + target_layout["w"] * 0.7
            ny = target_layout["y"] + target_layout["h"] * (0.42 + note_i * 0.2)
            note_bounds = [nx, ny, canvas.width * 0.088, canvas.height * 0.104]
            add_element(
                elements,
                note_id,
                "note",
                note["text"],
                note_bounds,
                note.get("actions", ["circle", "box"]),
                canvas,
                1.85,
                note_bounds,
                existing_annotation_ids,
            )
            parts.append(f'<g id="element-{note_id}" data-kind="note">')
            parts.append(rect(*note_bounds, "box", 10 * canvas.sx))
            note_lines = wrap_text(note["text"], 7)
            for line_i, line in enumerate(note_lines[:3]):
                parts.append(text(nx + note_bounds[2] / 2, ny + canvas.height * (0.04 + line_i * 0.032), line, "note"))
            parts.append(rect(*note_bounds, "target", 0))
            parts.append("</g>")

    parts.append("</svg>")

    manifest = {
        "canvas": {"width": canvas.width, "height": canvas.height},
        "image": source_image or "board.png",
        "source_image": source_image or "board.png",
        "coordinate_system": "board-image-pixels",
        "assetRef": asset_ref,
        "style": {
            "paper": PALETTE["paper"],
            "ink": PALETTE["ink"],
            "structure": PALETTE["teal"],
            "annotation": PALETTE["blue"],
            "highlight": PALETTE["amber"],
            "red": PALETTE["red"],
        },
        "elements": elements,
        "calibration": {
            "source": "board_spec_explicit_bboxes" if has_explicit_elements(spec) else "deterministic_control_layout",
            "warnings": warnings,
        },
    }
    return "\n".join(parts), manifest


def extract_segments(spec: dict[str, Any], voiceover_doc: Any | None) -> list[dict[str, Any]]:
    source = voiceover_doc if voiceover_doc is not None else spec
    if isinstance(source, list):
        return source
    if not isinstance(source, dict):
        raise ValueError("voiceover input must be an object or list")
    segments = source.get("segments") or source.get("voiceover_segments") or []
    if not isinstance(segments, list):
        raise ValueError("voiceover segments must be a list")
    return segments


def score_element_match(query: str, element: dict[str, Any]) -> float:
    query_text = (query or "").lower()
    if not query_text:
        return 0.0
    haystack = " ".join(
        str(value or "")
        for value in [
            element.get("id"),
            element.get("text"),
            element.get("kind"),
            (element.get("sourceKeyObject") or {}).get("role"),
            (element.get("sourceKeyObject") or {}).get("visualForm"),
        ]
    ).lower()
    score = 0.0
    for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", query_text):
        if token and token in haystack:
            score += max(1.0, min(6.0, len(token) / 2))
    query_chars = {ch for ch in query_text if re.match(r"[a-z0-9\u4e00-\u9fff]", ch)}
    haystack_chars = {ch for ch in haystack if re.match(r"[a-z0-9\u4e00-\u9fff]", ch)}
    score += len(query_chars & haystack_chars) * 0.25
    return score


def indexed_element(raw_target: str | None, elements: dict[str, dict[str, Any]]) -> str | None:
    if not raw_target:
        return None
    match = re.search(r"-item-(\d+)$", raw_target)
    if not match:
        return None
    index = int(match.group(1)) - 1
    candidates = [item["id"] for item in elements.values() if item["id"] != "title"]
    if 0 <= index < len(candidates):
        return candidates[index]
    return None


def resolve_element_id(
    raw_target: str | None,
    elements: dict[str, dict[str, Any]],
    context: dict[str, Any] | None = None,
    allow_remap: bool = False,
    remap_log: list[dict[str, Any]] | None = None,
) -> str:
    target = raw_target or "title"
    if target in elements:
        return target
    text_match = next((item["id"] for item in elements.values() if item.get("text") == target), None)
    if text_match:
        return text_match
    if allow_remap:
        context = context or {}
        anchor_query = str(context.get("spokenAnchor") or "")
        if anchor_query:
            anchor_scored = [
                (score_element_match(anchor_query, item), item["id"])
                for item in elements.values()
                if item["id"] != "title"
            ]
            anchor_scored.sort(reverse=True)
            anchor_score, anchor_id = anchor_scored[0] if anchor_scored else (0.0, None)
            if anchor_id and anchor_score > 0:
                if remap_log is not None:
                    remap_log.append(
                        {
                            "segment": context.get("segmentId"),
                            "from": target,
                            "to": anchor_id,
                            "reason": "spoken_anchor_match",
                            "score": round(anchor_score, 3),
                        }
                    )
                return anchor_id
        query = " ".join(
            str(value or "")
            for value in [
                target,
                anchor_query,
                context.get("caption"),
                context.get("targetElement"),
            ]
        )
        scored = [
            (score_element_match(query, item), item["id"])
            for item in elements.values()
            if item["id"] != "title"
        ]
        scored.sort(reverse=True)
        best_score, best_id = scored[0] if scored else (0.0, None)
        if best_id and best_score > 0:
            if remap_log is not None:
                remap_log.append(
                    {
                        "segment": context.get("segmentId"),
                        "from": target,
                        "to": best_id,
                        "reason": "fuzzy_text_match",
                        "score": round(best_score, 3),
                    }
                )
            return best_id
        index_match = indexed_element(target, elements)
        if index_match:
            if remap_log is not None:
                remap_log.append(
                    {
                        "segment": context.get("segmentId"),
                        "from": target,
                        "to": index_match,
                        "reason": "item_index_fallback",
                    }
                )
            return index_match
    raise ValueError(f"motion target '{target}' does not exist in board_manifest elements")


def annotation_for_action(element: dict[str, Any], action_type: str, requested_id: str | None, canvas: Canvas, existing: set[str]) -> str:
    annotations = element.setdefault("annotations", {})
    if requested_id and requested_id in annotations:
        return requested_id
    if requested_id:
        annotations[requested_id] = annotation_geometry(
            action_type,
            bbox(element.get("annotationTargetBbox") or element["bbox"]),
            canvas,
            requested_id,
        )
        existing.add(requested_id)
        element["actions"] = sorted({item["type"] for item in annotations.values()})
        return requested_id
    for annotation_id, annotation in annotations.items():
        if annotation.get("type") == action_type:
            return annotation_id
    add_annotations_to_element(element, [action_type], canvas, existing)
    for annotation_id, annotation in element["annotations"].items():
        if annotation.get("type") == action_type:
            return annotation_id
    raise ValueError(f"Could not create annotation '{action_type}' for element '{element['id']}'")


def segment_text(source: dict[str, Any]) -> str:
    return str(source.get("caption") or source.get("text") or source.get("voiceover") or "")


def spoken_anchor(source: dict[str, Any], action: dict[str, Any], index: int) -> tuple[str, str]:
    if action.get("spokenAnchor"):
        return str(action["spokenAnchor"]), "action.spokenAnchor"
    if source.get("spokenAnchor"):
        return str(source["spokenAnchor"]), "segment.spokenAnchor"
    anchors = source.get("spokenAnchors")
    if isinstance(anchors, list) and anchors:
        return str(anchors[min(index, len(anchors) - 1)]), "segment.spokenAnchors"
    text_value = segment_text(source)
    if text_value:
        return text_value, "segment.text"
    return source.get("id", f"segment-{index + 1}"), "segment.id"


def action_offset(
    source: dict[str, Any],
    action: dict[str, Any],
    action_index: int,
    action_count: int,
    anchor: str,
    speech_duration: float,
) -> float:
    if action.get("offset") is not None:
        return float(action["offset"])
    if action.get("anchorRatio") is not None:
        return max(0.0, min(speech_duration, speech_duration * float(action["anchorRatio"])))
    text_value = segment_text(source)
    if anchor and text_value and anchor in text_value and len(text_value) > 0:
        ratio = text_value.index(anchor) / max(1, len(text_value))
        return max(0.0, min(speech_duration, speech_duration * ratio))
    slot = (action_index + 1) / (action_count + 1)
    return max(0.0, min(speech_duration, speech_duration * slot))


def build_motion_plan(
    spec: dict[str, Any],
    manifest: dict[str, Any],
    voiceover_doc: Any | None,
    canvas: Canvas,
    allow_remap: bool = False,
    remap_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    elements = {item["id"]: item for item in manifest["elements"]}
    existing_annotation_ids = {annotation_id for item in elements.values() for annotation_id in item.get("annotations", {})}
    segments = []
    cursor_time = 0.0
    source_segments = extract_segments(spec, voiceover_doc)

    for i, source in enumerate(source_segments):
        target_context = {
            "segmentId": source.get("id", f"segment-{i + 1}"),
            "caption": segment_text(source),
            "spokenAnchor": " ".join(str(item) for item in source.get("spokenAnchors", []) if item)
            if isinstance(source.get("spokenAnchors"), list)
            else source.get("spokenAnchor"),
            "targetElement": source.get("targetElement") or source.get("target"),
        }
        target = resolve_element_id(
            source.get("targetElement") or source.get("target"),
            elements,
            target_context,
            allow_remap,
            remap_log,
        )
        element = elements[target]
        start = float(source.get("start", cursor_time))
        if source.get("speechEnd") is not None:
            speech_end = float(source["speechEnd"])
        elif source.get("end") is not None:
            speech_end = float(source["end"])
        else:
            speech_end = start + float(source.get("duration", 5.0))
        end = float(source.get("end", speech_end + float(source.get("pauseAfter", 0.0) or 0.0)))
        speech_duration = max(0.1, speech_end - start)

        raw_actions = source.get("actions")
        if not raw_actions:
            effect = source.get("effect")
            raw_actions = [] if effect in (None, "none", "camera") else [{"type": effect, "element": target}]

        actions: list[dict[str, Any]] = []
        for action_index, raw_action in enumerate(raw_actions):
            raw_action = dict(raw_action)
            action_type = normalize_annotation_type(raw_action.get("type") or raw_action.get("effect") or source.get("effect"))
            action_anchor, anchor_source = spoken_anchor(source, raw_action, action_index)
            action_context = {
                "segmentId": source.get("id", f"segment-{i + 1}"),
                "caption": segment_text(source),
                "spokenAnchor": action_anchor,
                "targetElement": raw_action.get("element") or raw_action.get("target") or target,
            }
            action_element_id = resolve_element_id(
                raw_action.get("element") or raw_action.get("target") or target,
                elements,
                action_context,
                allow_remap,
                remap_log,
            )
            action_element = elements[action_element_id]
            annotation_id = annotation_for_action(
                action_element,
                action_type,
                raw_action.get("annotation"),
                canvas,
                existing_annotation_ids,
            )
            duration = float(raw_action.get("duration", DEFAULT_ACTION_DURATION[action_type]))
            offset = action_offset(source, raw_action, action_index, len(raw_actions), action_anchor, speech_duration)
            offset = max(0.0, min(offset, max(0.0, speech_duration - min(duration, speech_duration * 0.8))))
            actions.append(
                {
                    "type": action_type,
                    "element": action_element_id,
                    "annotation": annotation_id,
                    "spokenAnchor": action_anchor,
                    "spokenAnchorSource": anchor_source,
                    "offset": round(offset, 3),
                    "duration": round(duration, 3),
                }
            )

        segments.append(
            {
                "id": source.get("id", f"segment-{i + 1}"),
                "start": round(start, 3),
                "speechEnd": round(speech_end, 3),
                "end": round(end, 3),
                "caption": source.get("caption") or source.get("text") or source.get("voiceover") or "",
                "boardId": source.get("boardId") or spec.get("id") or spec.get("boardId"),
                "target": target,
                "camera": source.get("camera") or element["camera"],
                "cursor": element["cursor"],
                "actions": actions,
            }
        )
        cursor_time = end

    overview_scale = min(1920 / canvas.width, 1080 / canvas.height)
    duration = max((segment["end"] for segment in segments), default=0)
    return {
        "sync_level": "voiceover-segment-action",
        "composition": {"width": 1920, "height": 1080, "duration": round(duration, 3)},
        "overview_camera": {
            "x": round(canvas.width / 2, 2),
            "y": round(canvas.height / 2, 2),
            "scale": round(overview_scale, 3),
        },
        "segments": segments,
    }


def build_annotation_manifest(manifest: dict[str, Any], motion: dict[str, Any]) -> dict[str, Any]:
    used = {
        action["annotation"]
        for segment in motion.get("segments", [])
        for action in segment.get("actions", [])
    }
    annotations: list[dict[str, Any]] = []
    for element in manifest["elements"]:
        for annotation_id, annotation in element.get("annotations", {}).items():
            row = {
                "id": annotation_id,
                "type": annotation["type"],
                "element": element["id"],
                "usedInMotionPlan": annotation_id in used,
                "bbox": element["bbox"],
                "camera": element["camera"],
                "cursor": element["cursor"],
            }
            for key, value in annotation.items():
                if key != "id":
                    row[key] = value
            annotations.append(row)
    return {
        "canvas": manifest["canvas"],
        "source_image": manifest.get("source_image", "board.png"),
        "coordinate_system": manifest.get("coordinate_system", "board-image-pixels"),
        "supportedTypes": list(SUPPORTED_ANNOTATIONS),
        "annotations": annotations,
    }


def build_image_prompt(spec: dict[str, Any], canvas: Canvas) -> str:
    sections = []
    for section in spec.get("sections", []):
        items = ", ".join(section.get("items", []))
        sections.append(f"- {section.get('title')}: {items}")
    for item in spec.get("elements", []) or spec.get("keyObjects", []):
        label = item.get("label") or item.get("text") or item.get("id")
        sections.append(f"- {label}: bbox {item.get('bbox')}")
    notes = "; ".join(note.get("text", "") for note in spec.get("notes", []))
    section_text = "\n".join(sections)
    return f"""# Hand-Drawn Image Prompt

## Stable Diffusion / Flux Prompt

"{spec['title']}, {spec.get('subtitle', '')}, large whiteboard infographic map, simple content density, hand-drawn educational diagram, continuous line art, engineer's notebook sketch, annotations in margins, ink on parchment background ({PALETTE['paper']}), charcoal ink lines ({PALETTE['ink']}), teal structural arrows and frames ({PALETTE['teal']}), amber highlight accents ({PALETTE['amber']}), ocean-blue annotations ({PALETTE['blue']}), slightly imperfect organic line variation, whiteboard explanation aesthetic"

Negative prompt:
"photorealistic, 3D render, CGI, stock photo, corporate flowchart, clean vector template, smooth digital art, gradient shading, airbrush, sterile presentation slide, crowded tiny text, too much text"

## Layout Content

{section_text}

Notes: {notes or 'none'}

## Technical Settings

- Aspect ratio: {canvas.width}:{canvas.height}
- Resolution: {canvas.width}x{canvas.height}
- Keep the same proportions as `board.svg` so `board_manifest.json` coordinates remain aligned.
- Keep text concise; do not copy the whole voiceover onto the board.
"""


def build_html(svg_name: str, title: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <style>
      html, body {{
        margin: 0;
        background: #151515;
      }}
      .frame {{
        width: min(100vw, calc(100vh * 16 / 9));
        aspect-ratio: 16 / 9;
        margin: 0 auto;
        background: #faf8f3;
        overflow: hidden;
      }}
      object {{
        display: block;
        width: 100%;
        height: 100%;
      }}
    </style>
  </head>
  <body>
    <div class="frame">
      <object data="{html.escape(svg_name)}" type="image/svg+xml" aria-label="{safe_title}"></object>
    </div>
  </body>
</html>
"""


def validate_package(manifest: dict[str, Any], motion: dict[str, Any], annotation_manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    elements = {item["id"]: item for item in manifest.get("elements", [])}
    annotations = {item["id"]: item for item in annotation_manifest.get("annotations", [])}
    for element in elements.values():
        for key in ("bbox", "camera", "cursor"):
            if key not in element:
                issues.append(f"element {element['id']} missing {key}")
        if element.get("annotations"):
            for annotation in element["annotations"].values():
                if annotation.get("type") not in SUPPORTED_ANNOTATIONS:
                    issues.append(f"annotation {annotation.get('id')} has unsupported type {annotation.get('type')}")
                if "cursorStart" not in annotation or "cursorEnd" not in annotation:
                    issues.append(f"annotation {annotation.get('id')} missing cursorStart/cursorEnd")
    for segment in motion.get("segments", []):
        for action in segment.get("actions", []):
            if not action.get("spokenAnchor"):
                issues.append(f"segment {segment.get('id')} action {action.get('annotation')} missing spokenAnchor")
            if action.get("element") not in elements:
                issues.append(f"segment {segment.get('id')} action targets missing element {action.get('element')}")
            if action.get("annotation") not in annotations:
                issues.append(f"segment {segment.get('id')} action targets missing annotation {action.get('annotation')}")
    return issues


def calibration_report(warnings: list[str], issues: list[str], source_image: str) -> str:
    status = "pass" if not issues else "failed"
    warning_lines = "\n".join(f"- {item}" for item in warnings) or "- none"
    issue_lines = "\n".join(f"- {item}" for item in issues) or "- none"
    return f"""# Board Calibration Report

Status: {status}

Source image: `{source_image}`

Coordinate rule: all bbox, cursor, and annotation geometry is expressed in board image pixels.

Warnings:
{warning_lines}

Validation issues:
{issue_lines}

Manual check:
- Open `board.svg` and `board.png` at the same canvas size.
- Verify each `annotation_manifest.json` coordinate sits on the intended text or shape.
- If an AI-generated PNG drifted from the control layout, write corrected element bboxes into `board_spec.json` and regenerate.
"""


def generate_single_board_package(
    spec: dict[str, Any],
    out: Path,
    voiceover_doc: Any | None,
    board_image: Path | None = None,
    asset_ref: dict[str, Any] | None = None,
    allow_remap: bool = False,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    canvas, warnings = canvas_from_inputs(spec, board_image)
    warnings.extend(extra_warnings or [])
    out.mkdir(parents=True, exist_ok=True)

    source_image = (asset_ref.get("localPath") or asset_ref.get("uri") or "board.png") if asset_ref else "board.png"
    if board_image:
        destination = out / source_image
        if board_image.resolve() != destination.resolve():
            shutil.copyfile(board_image, destination)

    remap_log: list[dict[str, Any]] = []
    svg, manifest = build_svg_and_manifest(spec, canvas, source_image, warnings, asset_ref)
    motion = build_motion_plan(spec, manifest, voiceover_doc, canvas, allow_remap, remap_log)
    annotation_manifest = build_annotation_manifest(manifest, motion)
    issues = validate_package(manifest, motion, annotation_manifest)
    if issues:
        raise ValueError("Board package validation failed:\n- " + "\n- ".join(issues))

    normalized_spec = dict(spec)
    normalized_spec["canvas"] = {"width": canvas.width, "height": canvas.height}

    (out / "board.svg").write_text(svg, encoding="utf-8")
    (out / "board.html").write_text(build_html("board.svg", spec["title"]), encoding="utf-8")
    (out / "image_prompt.md").write_text(build_image_prompt(spec, canvas), encoding="utf-8")
    (out / "calibration_report.md").write_text(calibration_report(warnings, issues, source_image), encoding="utf-8")
    write_json(out / "board_spec.json", normalized_spec)
    write_json(out / "board_manifest.json", manifest)
    write_json(out / "motion_plan.json", motion)
    write_json(out / "annotation_manifest.json", annotation_manifest)

    return {
        "boardId": spec.get("id") or spec.get("boardId"),
        "title": spec.get("title"),
        "path": str(out),
        "sourceImage": source_image,
        "assetRef": asset_ref,
        "counts": {
            "elements": len(manifest.get("elements", [])),
            "annotations": len(annotation_manifest.get("annotations", [])),
            "motionSegments": len(motion.get("segments", [])),
            "motionActions": sum(len(segment.get("actions", [])) for segment in motion.get("segments", [])),
        },
        "warnings": warnings,
        "issues": issues,
        "remaps": remap_log,
        "motion": motion,
    }


def default_project_path(project: Path, relative: str) -> Path:
    return project / relative


def load_project_inputs(
    project: Path,
    asset_manifest_path: Path | None,
    voiceover_path: Path | None,
    infographic_plan_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path, Path]:
    asset_path = asset_manifest_path or default_project_path(project, "board_asset_manifest.json")
    voice_path = voiceover_path or default_project_path(project, "script/voiceover_segments.json")
    plan_path = infographic_plan_path or default_project_path(project, "infographic/infographic_plan.json")
    return read_json(asset_path), read_json(voice_path), read_json(plan_path), asset_path, voice_path, plan_path


def board_source_segment_map(infographic_plan: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for board in infographic_plan.get("boards", []):
        board_id = board.get("id")
        for segment_id in board.get("sourceSegments", []):
            if board_id:
                mapping[str(segment_id)] = str(board_id)
    return mapping


def assign_segments_to_boards(
    voiceover_doc: dict[str, Any],
    board_ids: set[str],
    source_segment_map: dict[str, str],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    assigned = {board_id: [] for board_id in board_ids}
    unmatched: list[dict[str, Any]] = []
    board_overrides: list[dict[str, Any]] = []
    for segment in voiceover_doc.get("segments", []):
        segment_id = segment.get("id")
        original_board = segment.get("boardId")
        mapped_board = source_segment_map.get(segment_id)
        board_id = mapped_board or original_board
        if board_id in assigned:
            cloned = copy.deepcopy(segment)
            if original_board and original_board != board_id:
                cloned["inputBoardId"] = original_board
                board_overrides.append(
                    {
                        "segment": segment_id,
                        "inputBoardId": original_board,
                        "assignedBoardId": board_id,
                        "reason": "infographic_plan.sourceSegments",
                    }
                )
            cloned["boardId"] = board_id
            assigned[board_id].append(cloned)
        else:
            unmatched.append(
                {
                    "segment": segment_id,
                    "inputBoardId": original_board,
                    "mappedBoardId": mapped_board,
                    "reason": "no boardId matched asset manifest or infographic plan",
                }
            )
    return assigned, unmatched, board_overrides


def board_specs_from_plan(project: Path, infographic_plan: dict[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for board in infographic_plan.get("boards", []):
        board_id = board.get("id")
        spec_path = board.get("boardSpecPath")
        if board_id and spec_path:
            paths[board_id] = project / spec_path
    return paths


def asset_entries(asset_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for board in asset_manifest.get("boards", []):
        board_id = board.get("boardId")
        if board_id:
            entries[board_id] = board
    return entries


def resolve_asset_for_board(
    project: Path,
    asset_manifest_path: Path,
    board_asset: dict[str, Any],
    board_out: Path,
) -> tuple[Path | None, dict[str, Any], list[str]]:
    warnings: list[str] = []
    asset = dict(board_asset.get("asset") or {})
    kind = asset.get("kind")
    uri = asset.get("uri")
    asset_ref = {
        "manifest": str(asset_manifest_path),
        "boardId": board_asset.get("boardId"),
        "kind": kind,
        "uri": uri,
        "width": asset.get("width"),
        "height": asset.get("height"),
        "sourcePrompt": asset.get("sourcePrompt"),
        "creatorOutput": asset.get("creatorOutput"),
    }
    if kind in {"file", "svg_preview"}:
        if not uri:
            raise ValueError(f"asset for {board_asset.get('boardId')} missing uri")
        source_path = (asset_manifest_path.parent / uri).resolve()
        if not source_path.exists():
            source_path = (project / uri).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"asset file not found for {board_asset.get('boardId')}: {uri}")
        if source_path.suffix.lower() == ".png":
            asset_ref["localPath"] = "board.png"
            return source_path, asset_ref, warnings
        local_name = f"board_asset{source_path.suffix.lower() or '.asset'}"
        shutil.copyfile(source_path, board_out / local_name)
        asset_ref["localPath"] = local_name
        warnings.append(f"asset kind {kind} is not PNG; copied {uri} as {local_name} and used board_spec canvas for control coordinates.")
        return None, asset_ref, warnings
    if kind == "url":
        asset_ref["localPath"] = None
        asset_ref["remoteUrl"] = uri
        warnings.append("url asset is pass-through; download/local calibration is not implemented in D yet.")
        return None, asset_ref, warnings
    if kind == "inline_generation":
        asset_ref["localPath"] = None
        warnings.append("inline_generation is for visual approval only; convert it to file or url before local calibration.")
        return None, asset_ref, warnings
    raise ValueError(f"unsupported asset.kind for {board_asset.get('boardId')}: {kind}")


def write_package_report(
    path: Path,
    board_summaries: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    board_overrides: list[dict[str, Any]],
) -> None:
    lines = ["# Multi-Board Package Report", ""]
    lines.append("## Boards")
    for summary in board_summaries:
        asset_ref = summary.get("assetRef") or {}
        counts = summary.get("counts") or {}
        lines.extend(
            [
                "",
                f"### {summary.get('boardId')}",
                f"- title: {summary.get('title')}",
                f"- asset.kind: {asset_ref.get('kind')}",
                f"- asset.uri: {asset_ref.get('uri')}",
                f"- elements: {counts.get('elements', 0)}",
                f"- annotations: {counts.get('annotations', 0)}",
                f"- motion segments: {counts.get('motionSegments', 0)}",
                f"- motion actions: {counts.get('motionActions', 0)}",
                f"- remaps: {len(summary.get('remaps') or [])}",
                f"- warnings: {len(summary.get('warnings') or [])}",
            ]
        )
    lines.extend(["", "## Voiceover Board Overrides"])
    if board_overrides:
        lines.extend(
            f"- {item['segment']}: {item['inputBoardId']} -> {item['assignedBoardId']} ({item['reason']})"
            for item in board_overrides
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Target Remaps"])
    remap_rows = [row for summary in board_summaries for row in summary.get("remaps", [])]
    if remap_rows:
        lines.extend(
            f"- {row.get('segment')}: {row.get('from')} -> {row.get('to')} ({row.get('reason')}, score={row.get('score', 'n/a')})"
            for row in remap_rows
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Unmatched Voiceover Segments"])
    if unmatched:
        lines.extend(f"- {item.get('segment')}: {item.get('reason')}" for item in unmatched)
    else:
        lines.append("- none")
    lines.extend(["", "## Missing Actions Or Coordinates"])
    missing = [
        issue
        for summary in board_summaries
        for issue in summary.get("issues", [])
    ]
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- none")
    lines.extend(["", "## Manual Calibration Notes"])
    lines.append("- Generated control coordinates are deterministic first drafts.")
    lines.append("- Preferred correction path: write `calibration/<boardId>.element_bboxes.json` and regenerate.")
    lines.append("- Legacy correction path: write explicit `elements[*].bbox` into each board_spec and regenerate.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_project_package(
    project: Path,
    output: Path,
    asset_manifest_path: Path | None,
    voiceover_path: Path | None,
    infographic_plan_path: Path | None,
    calibration_dir: Path | None = None,
) -> dict[str, Any]:
    asset_manifest, voiceover_doc, infographic_plan, asset_path, voice_path, plan_path = load_project_inputs(
        project,
        asset_manifest_path,
        voiceover_path,
        infographic_plan_path,
    )
    board_assets = asset_entries(asset_manifest)
    spec_paths = board_specs_from_plan(project, infographic_plan)
    board_ids = set(board_assets) | set(spec_paths)
    source_map = board_source_segment_map(infographic_plan)
    assigned_segments, unmatched, board_overrides = assign_segments_to_boards(voiceover_doc, board_ids, source_map)
    output.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    combined_segments: list[dict[str, Any]] = []
    for board_id in sorted(board_ids):
        if board_id not in spec_paths:
            raise ValueError(f"missing board_spec for {board_id}")
        if board_id not in board_assets:
            raise ValueError(f"missing asset manifest entry for {board_id}")
        spec = load_spec(spec_paths[board_id])
        spec["id"] = spec.get("id") or board_id
        calibration, calibration_path = load_calibration(calibration_dir, board_id)
        calibration_warnings: list[str] = []
        spec = apply_calibration(spec, calibration, calibration_path, calibration_warnings)
        board_out = output / board_id
        board_out.mkdir(parents=True, exist_ok=True)
        board_image, asset_ref, asset_warnings = resolve_asset_for_board(project, asset_path, board_assets[board_id], board_out)
        per_board_voiceover = {
            "segments": assigned_segments.get(board_id, []),
            "topic": voiceover_doc.get("topic"),
            "style": voiceover_doc.get("style"),
        }
        summary = generate_single_board_package(
            spec,
            board_out,
            per_board_voiceover,
            board_image,
            asset_ref,
            allow_remap=True,
            extra_warnings=asset_warnings + calibration_warnings,
        )
        summary["boardSpecPath"] = str(spec_paths[board_id])
        summary["relativePath"] = board_id
        summaries.append(summary)
        combined_segments.extend(copy.deepcopy(summary["motion"].get("segments", [])))

    generated_by_id = {
        str(segment.get("id")): segment
        for segment in combined_segments
        if segment.get("id") is not None
    }
    voiceover_order = [
        str(segment.get("id", f"segment-{index + 1}"))
        for index, segment in enumerate(voiceover_doc.get("segments", []))
        if str(segment.get("id", f"segment-{index + 1}")) in generated_by_id
    ]
    remaining_order = [segment_id for segment_id in generated_by_id if segment_id not in voiceover_order]
    ordered_segment_ids = voiceover_order + remaining_order
    combined_segments = []
    timeline_cursor = 0.0
    for segment_id in ordered_segment_ids:
        segment = copy.deepcopy(generated_by_id[segment_id])
        local_start = float(segment.get("start", 0.0) or 0.0)
        local_speech_end = float(segment.get("speechEnd", segment.get("end", local_start)) or local_start)
        local_end = float(segment.get("end", local_speech_end) or local_speech_end)
        speech_duration = max(0.0, local_speech_end - local_start)
        segment_duration = max(speech_duration, local_end - local_start)
        segment["start"] = round(timeline_cursor, 3)
        segment["speechEnd"] = round(timeline_cursor + speech_duration, 3)
        segment["end"] = round(timeline_cursor + segment_duration, 3)
        timeline_cursor += segment_duration
        combined_segments.append(segment)
    duration = timeline_cursor
    combined_motion = {
        "sync_level": "multi-board-voiceover-segment-action",
        "composition": {"width": 1920, "height": 1080, "duration": round(duration, 3)},
        "boards": [
            {
                "boardId": summary["boardId"],
                "path": summary["relativePath"],
                "motionPlan": f"{summary['relativePath']}/motion_plan.json",
                "boardManifest": f"{summary['relativePath']}/board_manifest.json",
                "annotationManifest": f"{summary['relativePath']}/annotation_manifest.json",
                "asset": summary.get("assetRef"),
            }
            for summary in summaries
        ],
        "segments": combined_segments,
    }
    board_index = {
        "version": "0.1",
        "project": str(project),
        "sources": {
            "assetManifest": str(asset_path),
            "voiceoverSegments": str(voice_path),
            "infographicPlan": str(plan_path),
        },
        "boards": [
            {
                "boardId": summary["boardId"],
                "title": summary["title"],
                "path": summary["relativePath"],
                "asset": summary.get("assetRef"),
                "counts": summary.get("counts"),
                "warnings": summary.get("warnings"),
                "remaps": summary.get("remaps"),
            }
            for summary in summaries
        ],
        "unmatchedVoiceoverSegments": unmatched,
        "boardOverrides": board_overrides,
        "combinedMotionPlan": "combined_motion_plan.json",
        "packageReport": "package_report.md",
    }
    write_json(output / "combined_motion_plan.json", combined_motion)
    write_json(output / "board_index.json", board_index)
    write_package_report(output / "package_report.md", summaries, unmatched, board_overrides)
    return board_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Path to board_spec.json for single-board mode")
    parser.add_argument("--output", required=True, type=Path, help="Output directory")
    parser.add_argument("--board-image", type=Path, help="Optional board.png to copy into the package and use for canvas size")
    parser.add_argument("--voiceover", type=Path, help="Optional voiceover_segments.json. Falls back to board_spec voiceover_segments.")
    parser.add_argument("--project", type=Path, help="Project package root for multi-board mode")
    parser.add_argument("--asset-manifest", type=Path, help="board_asset_manifest.json for multi-board mode")
    parser.add_argument("--infographic-plan", type=Path, help="infographic_plan.json for multi-board mode")
    parser.add_argument(
        "--calibration-dir",
        type=Path,
        help="Optional directory with board-XX.element_bboxes.json calibration files. Defaults to <project>/calibration in project mode.",
    )
    args = parser.parse_args()

    if args.project:
        calibration_dir = args.calibration_dir if args.calibration_dir else args.project / "calibration"
        index = generate_project_package(
            args.project,
            args.output,
            args.asset_manifest,
            args.voiceover,
            args.infographic_plan,
            calibration_dir if calibration_dir.exists() else None,
        )
        print(f"Generated multi-board package: {args.output}")
        print(f"- boards: {len(index.get('boards', []))}")
        print("- board_index.json")
        print("- combined_motion_plan.json")
        print("- package_report.md")
        return

    if not args.input:
        raise SystemExit("--input is required unless --project is set")

    spec = load_spec(args.input)
    board_id = spec.get("id") or spec.get("boardId") or args.input.stem.replace(".board_spec", "")
    calibration_dir = args.calibration_dir
    calibration, calibration_path = load_calibration(calibration_dir, str(board_id))
    calibration_warnings: list[str] = []
    spec = apply_calibration(spec, calibration, calibration_path, calibration_warnings)
    voiceover_doc = read_json(args.voiceover) if args.voiceover else None
    generate_single_board_package(spec, args.output, voiceover_doc, args.board_image, extra_warnings=calibration_warnings)

    print(f"Generated board package: {args.output}")
    print("- board.svg")
    print("- board.html")
    print("- board_spec.json")
    print("- board_manifest.json")
    print("- motion_plan.json")
    print("- annotation_manifest.json")
    print("- image_prompt.md")
    print("- calibration_report.md")
    if args.board_image:
        print("- board.png")


if __name__ == "__main__":
    main()
