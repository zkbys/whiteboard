#!/usr/bin/env python3
"""Auto-calibrate whiteboard element bboxes from the actual board PNG.

Reads images/<boardId>.model-generated.png and infographic/board_specs/*.board_spec.json,
detects text/element positions using a VLM or OCR backend, and writes
calibration/<boardId>.element_bboxes.json for D to consume.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from _auto_calibrate import (
    AgentBackend,
    CalibrationBackend,
    MockBackend,
    OcrBackend,
    VlmBackend,
    build_calibrated_element,
    match_candidates,
    resolve_backend,
)
from _auto_calibrate.geometry import Box


REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_TOOL = REPO_ROOT / "hand-drawn-infographic-video-board" / "scripts" / "create_calibration_tool.py"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-calibrate whiteboard element bboxes from model-generated PNGs."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--provider",
        choices=("auto", "agent", "vlm", "ocr", "mock"),
        default="auto",
        help="Detection backend. auto tries configured agent, then vlm, then ocr, then mock/manual.",
    )
    parser.add_argument("--vlm-model", default=os.environ.get("WHITEBOARD_CALIBRATION_VLM_MODEL", "gpt-4o"))
    parser.add_argument("--vlm-base-url", default=os.environ.get("OPENAI_BASE_URL"))
    parser.add_argument("--api-key-env", default=os.environ.get("WHITEBOARD_CALIBRATION_API_KEY_ENV", "OPENAI_API_KEY"))
    parser.add_argument("--agent-model", default=os.environ.get("WHITEBOARD_CALIBRATION_AGENT_MODEL", "claude-opus-4-8"))
    parser.add_argument("--agent-base-url", default=os.environ.get("ANTHROPIC_BASE_URL"))
    parser.add_argument(
        "--agent-api-key-env",
        default=os.environ.get("WHITEBOARD_CALIBRATION_AGENT_API_KEY_ENV", "ANTHROPIC_AUTH_TOKEN"),
    )
    parser.add_argument("--ocr-backend", choices=("auto", "easyocr", "paddleocr"), default="auto")
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--write-tool-on-partial", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_board_ids(project_dir: Path) -> list[str]:
    """Discover board IDs from infographic plan or images."""
    plan_path = project_dir / "infographic" / "infographic_plan.json"
    if plan_path.exists():
        plan = read_json(plan_path)
        boards = [
            str(board.get("id") or board.get("boardId"))
            for board in plan.get("boards", [])
            if board.get("id") or board.get("boardId")
        ]
        if boards:
            return boards

    images_dir = project_dir / "images"
    boards = []
    for path in sorted(images_dir.glob("*.model-generated.png")):
        boards.append(path.name.removesuffix(".model-generated.png"))
    return boards


def find_board_spec(project_dir: Path, board_id: str) -> Path | None:
    """Find board_spec.json for a board."""
    plan_path = project_dir / "infographic" / "infographic_plan.json"
    if plan_path.exists():
        plan = read_json(plan_path)
        for board in plan.get("boards", []):
            bid = str(board.get("id") or board.get("boardId", ""))
            if bid == board_id:
                spec_path = board.get("boardSpecPath")
                if spec_path:
                    return project_dir / spec_path

    candidates = [
        project_dir / "infographic" / "board_specs" / f"{board_id}.board_spec.json",
        project_dir / "infographic" / "board_specs" / f"{board_id}.json",
        project_dir / "infographic" / f"{board_id}.board_spec.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_board_image(project_dir: Path, board_id: str) -> Path | None:
    """Find the model-generated PNG for a board."""
    candidates = [
        project_dir / "images" / f"{board_id}.model-generated.png",
        project_dir / "board_source_for_e" / board_id / "board.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a valid PNG")
    import struct

    return struct.unpack(">II", header[16:24])


def extract_candidates(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract calibratable element candidates from a board spec."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    title = spec.get("title")
    if title:
        candidates.append({"id": "title", "label": str(title), "kind": "title", "role": "title"})
        seen.add("title")

    for raw in spec.get("elements", []) or []:
        element_id = raw.get("id")
        if not element_id or element_id in seen:
            continue
        candidates.append(
            {
                "id": str(element_id),
                "label": raw.get("text") or raw.get("label") or str(element_id),
                "kind": raw.get("kind") or raw.get("role") or "element",
                "role": raw.get("role"),
                "actions": raw.get("actions") or raw.get("annotationTypes"),
            }
        )
        seen.add(str(element_id))

    for raw in spec.get("keyObjects", []) or []:
        element_id = raw.get("id")
        if not element_id or element_id in seen:
            continue
        candidates.append(
            {
                "id": str(element_id),
                "label": raw.get("label") or raw.get("text") or str(element_id),
                "kind": raw.get("role") or "element",
                "role": raw.get("role"),
                "actions": raw.get("actions") or ([raw.get("annotationIntent")] if raw.get("annotationIntent") else None),
            }
        )
        seen.add(str(element_id))

    return candidates


def extract_required_ids(project_dir: Path, board_id: str) -> set[str]:
    """Extract element IDs that must be calibrated for a board."""
    required: set[str] = {"title"}
    voiceover_path = project_dir / "script" / "voiceover_segments.json"
    if not voiceover_path.exists():
        return required

    voiceover = read_json(voiceover_path)
    for segment in voiceover.get("segments", []):
        if segment.get("boardId") != board_id:
            continue
        target = segment.get("targetElement")
        if target:
            required.add(str(target))
        for action in segment.get("actions", []):
            element = action.get("element")
            if element:
                required.add(str(element))
    return required


def derive_canvas_size(spec: dict[str, Any], image_path: Path) -> tuple[float, float]:
    """Use the PNG dimensions as the coordinate system when available."""
    try:
        return png_size(image_path)
    except ValueError:
        canvas = spec.get("canvas", {})
        w = canvas.get("width")
        h = canvas.get("height")
        if w and h:
            return float(w), float(h)
        return 1920.0, 1080.0


def resolve_auto_provider(project_dir: Path, args: argparse.Namespace) -> CalibrationBackend:
    """Resolve the auto provider by probing available backends."""
    env_provider = os.environ.get("WHITEBOARD_CALIBRATION_PROVIDER", "").strip().lower()
    if env_provider and env_provider != "auto":
        kwargs = {k: v for k, v in vars(args).items() if k != "provider"}
        return resolve_backend(env_provider, **kwargs)

    agent_explicit = (
        os.environ.get("WHITEBOARD_CALIBRATION_AGENT_AUTO", "").strip() == "1"
    )
    openai_key = os.environ.get(args.api_key_env)
    anthropic_key = os.environ.get(args.agent_api_key_env)
    if agent_explicit or (anthropic_key and not openai_key):
        agent = AgentBackend(
            model=args.agent_model,
            api_key_env=args.agent_api_key_env,
            base_url_env="ANTHROPIC_BASE_URL",
            timeout=args.timeout,
        )
        if agent.is_available():
            return agent

    vlm = VlmBackend(
        model=args.vlm_model,
        base_url=args.vlm_base_url,
        api_key_env=args.api_key_env,
        timeout=args.timeout,
    )
    if vlm.is_available():
        return vlm

    ocr = OcrBackend(backend=args.ocr_backend)
    if ocr.is_available():
        return ocr

    return MockBackend()


def calibrate_board(
    project_dir: Path,
    board_id: str,
    backend: CalibrationBackend,
    min_confidence: float,
) -> dict[str, Any]:
    """Calibrate a single board and return a report entry."""
    image_path = find_board_image(project_dir, board_id)
    if not image_path:
        return {
            "boardId": board_id,
            "status": "error",
            "error": f"Board image not found for {board_id}",
        }

    spec_path = find_board_spec(project_dir, board_id)
    spec: dict[str, Any] = read_json(spec_path) if spec_path else {"id": board_id}
    candidates = extract_candidates(spec)
    if not candidates:
        return {
            "boardId": board_id,
            "status": "error",
            "error": f"No calibratable elements in board spec for {board_id}",
        }

    canvas_w, canvas_h = derive_canvas_size(spec, image_path)
    required_ids = extract_required_ids(project_dir, board_id)
    candidate_ids = {c["id"] for c in candidates}
    required_candidates = [c for c in candidates if c["id"] in required_ids]
    if not required_candidates:
        required_candidates = candidates

    detected = backend.detect(image_path, required_candidates)
    matches = match_candidates(
        [{"text": d.text, "bbox": d.bbox, "confidence": d.confidence} for d in detected],
        required_candidates,
        min_confidence=min_confidence,
    )

    elements: list[dict[str, Any]] = []
    matched_ids: set[str] = set()
    review: list[dict[str, Any]] = []

    # Report required targets that are missing from the board spec entirely.
    for missing_id in sorted(required_ids - candidate_ids):
        review.append(
            {
                "id": missing_id,
                "reason": "required targetElement not found in board_spec",
            }
        )

    for match in matches:
        candidate = match["candidate"]
        element_id = str(match["id"])
        if match["matched"]:
            bbox = match["bbox"]
            if not isinstance(bbox, list) or len(bbox) != 4:
                review.append({"id": element_id, "reason": "invalid bbox from detector"})
                continue
            try:
                Box.from_list(bbox).clamp(canvas_w, canvas_h)
            except ValueError as exc:
                review.append({"id": element_id, "reason": str(exc)})
                continue
            elements.append(
                build_calibrated_element(
                    element_id=element_id,
                    text=str(candidate.get("label") or candidate.get("text") or element_id),
                    kind=str(candidate.get("kind") or candidate.get("role") or "element"),
                    role=candidate.get("role"),
                    bbox=bbox,
                    actions=candidate.get("actions"),
                    canvas_w=canvas_w,
                    canvas_h=canvas_h,
                )
            )
            matched_ids.add(element_id)
        else:
            review.append(
                {
                    "id": element_id,
                    "reason": "no confident match",
                    "bestConfidence": match.get("confidence"),
                    "bestText": match.get("detectedText"),
                }
            )

    calibration_file = project_dir / "calibration" / f"{board_id}.element_bboxes.json"
    status = "complete" if not review else "partial"
    result: dict[str, Any] = {
        "boardId": board_id,
        "status": status,
        "provider": backend.name,
        "imagePath": str(image_path.relative_to(project_dir) if image_path.is_relative_to(project_dir) else image_path),
        "canvas": {"width": canvas_w, "height": canvas_h},
        "matchedCount": len(elements),
        "requiredCount": len(required_ids),
        "requiredIds": sorted(required_ids),
        "matchedIds": sorted(matched_ids),
        "review": review,
        "calibrationFile": str(calibration_file.relative_to(project_dir)),
    }

    if elements:
        write_json(calibration_file, {"boardId": board_id, "canvas": result["canvas"], "elements": elements})

    return result


def write_calibration_tool(
    project_dir: Path,
    report: dict[str, Any],
    prefill_report_path: Path,
) -> None:
    """Generate the browser calibration tool pre-filled with auto results."""
    command = [
        sys.executable,
        str(CALIBRATION_TOOL),
        "--project",
        str(project_dir),
        "--calibration-dir",
        str(project_dir / "calibration"),
        "--output-dir",
        str(project_dir / "calibration_tool"),
        "--prefill-from",
        str(prefill_report_path),
        "--overwrite",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(
            f"[auto-calibrate] warning: calibration tool generation failed (exit {result.returncode})",
            file=sys.stderr,
        )
        if result.stderr:
            print(result.stderr, file=sys.stderr)


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()

    if not project_dir.is_dir():
        print(f"ERROR: project directory not found: {project_dir}", file=sys.stderr)
        return 2

    board_ids = load_board_ids(project_dir)
    if not board_ids:
        print(f"ERROR: no boards found in {project_dir}", file=sys.stderr)
        return 2

    if args.provider == "auto":
        backend = resolve_auto_provider(project_dir, args)
    else:
        backend = resolve_backend(
            args.provider,
            vlm_model=args.vlm_model,
            vlm_base_url=args.vlm_base_url,
            api_key_env=args.api_key_env,
            timeout=args.timeout,
            ocr_backend=args.ocr_backend,
            agent_model=args.agent_model,
            agent_base_url_env="ANTHROPIC_BASE_URL",
            agent_api_key_env=args.agent_api_key_env,
        )

    if args.dry_run and hasattr(backend, "dry_run_info"):
        info = backend.dry_run_info(find_board_image(project_dir, board_ids[0]) or Path(), [])
        print(json.dumps({"dryRun": True, backend.name: info}, ensure_ascii=False, indent=2))
        return 0

    board_reports: list[dict[str, Any]] = []
    overall_status = "complete"
    for board_id in board_ids:
        report = calibrate_board(project_dir, board_id, backend, args.min_confidence)
        board_reports.append(report)
        if report.get("status") != "complete":
            overall_status = "partial"
        if report.get("status") == "error":
            overall_status = "error"

    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "status": overall_status,
        "provider": backend.name,
        "projectDir": str(project_dir),
        "boards": board_reports,
    }

    report_path = project_dir / "calibration" / "auto_calibration_report.json"
    write_json(report_path, summary)

    if overall_status == "partial" and args.write_tool_on_partial:
        write_calibration_tool(project_dir, summary, report_path)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"auto-calibration status: {overall_status}")
        print(f"report: {report_path}")
        for report in board_reports:
            print(
                f"  {report['boardId']}: {report['status']} "
                f"({report['matchedCount']}/{report['requiredCount']} matched)"
            )
            for item in report.get("review", []):
                print(f"    needs review: {item['id']} ({item['reason']})")

    if overall_status == "complete":
        return 0
    if overall_status == "partial":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
