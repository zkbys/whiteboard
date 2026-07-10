#!/usr/bin/env python3
"""Validate a completed whiteboard-video project against the v1 release contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_asset_identity import run_check as run_identity_check
from write_board_asset_manifest import read_png_size


REQUIRED_FILES = (
    "script/voiceover_segments.json",
    "script/visual_beats.json",
    "infographic/infographic_plan.json",
    "image_generation_report.json",
    "board_asset_manifest.json",
    "board_source_for_e/board_index.json",
    "board_source_for_e/combined_motion_plan.json",
    "audio/narration.wav",
    "audio/voiceover_timing.json",
    "audio/word_timing.json",
    "audio/captions.srt",
    "sync/action_timing.json",
    "sync/camera_plan.json",
    "sync/action_camera_qa_report.md",
    "sync/action_camera_qa_report.json",
    "video/hyperframes/index.html",
    "video/hyperframes/DESIGN.md",
    "video/hyperframes/hyperframes.json",
    "video/hyperframes/package.json",
    "video/preview.mp4",
    "video/keyframes/keyframe_manifest.json",
    "video/keyframes/contact_sheet_start.jpg",
    "video/keyframes/contact_sheet_done.jpg",
    "video/renderer_report.json",
    "integration_report.md",
)

PUBLIC_FIXTURE_SHA256 = "51a0c064a4c7b4afbfa25d6c8e5e2640bbe124c86cbe622413fafb541d800dfb"
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".srt", ".txt", ".vtt"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one completed whiteboard-video project for v1 release acceptance."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--ffprobe", help="ffprobe executable; defaults to PATH lookup.")
    parser.add_argument("--min-duration", type=float, default=30.0)
    parser.add_argument("--max-duration", type=float, default=60.0)
    parser.add_argument("--max-duration-delta", type=float, default=0.1)
    parser.add_argument(
        "--forbid-prefix",
        action="append",
        default=[],
        help="Fail when a text output contains this obsolete source prefix. Repeatable.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    return parser.parse_args()


def add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    message: str,
    **details: Any,
) -> None:
    item: dict[str, Any] = {
        "id": check_id,
        "status": "PASS" if passed else "FAIL",
        "message": message,
    }
    if details:
        item["details"] = details
    checks.append(item)


def read_json(path: Path, checks: list[dict[str, Any]], check_id: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add_check(checks, check_id, False, f"Cannot read valid JSON: {path}", error=str(exc))
        return None


def inside_project(path: Path, project_dir: Path) -> bool:
    try:
        path.resolve().relative_to(project_dir)
        return True
    except ValueError:
        return False


def resolve_output_path(value: str, project_dir: Path, fallback_root: Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        return raw.resolve()
    project_candidate = (project_dir / raw).resolve()
    if project_candidate.exists():
        return project_candidate
    return (fallback_root / raw).resolve()


def probe_duration(ffprobe: str, preview: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(preview),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"ffprobe exited {result.returncode}")
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def check_required_files(project_dir: Path, checks: list[dict[str, Any]]) -> None:
    missing = [
        relative
        for relative in REQUIRED_FILES
        if not (project_dir / relative).is_file() or (project_dir / relative).stat().st_size == 0
    ]
    add_check(
        checks,
        "files.required",
        not missing,
        "All required v1 project files exist." if not missing else "Required v1 files are missing.",
        missing=missing,
    )


def check_images(project_dir: Path, checks: list[dict[str, Any]]) -> None:
    generation_path = project_dir / "image_generation_report.json"
    manifest_path = project_dir / "board_asset_manifest.json"
    if not generation_path.is_file() or not manifest_path.is_file():
        return
    generation = read_json(generation_path, checks, "images.generation_json")
    manifest = read_json(manifest_path, checks, "images.manifest_json")
    if not isinstance(generation, dict) or not isinstance(manifest, dict):
        return

    generation_boards = generation.get("boards")
    valid_generation = (
        generation.get("status") == "complete"
        and generation.get("manifestPath") == "board_asset_manifest.json"
        and isinstance(generation_boards, list)
        and bool(generation_boards)
        and all(board.get("status") in {"generated", "reused"} for board in generation_boards)
    )
    add_check(
        checks,
        "images.generation",
        valid_generation,
        "Image generation completed for every board."
        if valid_generation
        else "Image generation report is incomplete or contains unresolved boards.",
        provider=generation.get("providerResolved"),
        automatic=generation.get("automatic"),
    )

    manifest_boards = manifest.get("boards")
    manifest_errors: list[str] = []
    manifest_ids: list[str] = []
    if not isinstance(manifest_boards, list) or not manifest_boards:
        manifest_errors.append("manifest contains no boards")
    else:
        for board in manifest_boards:
            board_id = board.get("boardId")
            asset = board.get("asset") or {}
            if not board_id:
                manifest_errors.append("board missing boardId")
                continue
            manifest_ids.append(str(board_id))
            if asset.get("kind") != "file":
                manifest_errors.append(f"{board_id}: asset.kind must be file")
                continue
            uri = asset.get("uri")
            expected_uri = f"images/{board_id}.model-generated.png"
            if uri != expected_uri:
                manifest_errors.append(f"{board_id}: asset URI must be {expected_uri}")
                continue
            asset_path = (project_dir / uri).resolve()
            if not inside_project(asset_path, project_dir):
                manifest_errors.append(f"{board_id}: asset escapes project directory")
                continue
            try:
                width, height = read_png_size(asset_path)
                if width < 512 or height < 512:
                    manifest_errors.append(f"{board_id}: PNG is only {width}x{height}")
                if asset.get("width") != width or asset.get("height") != height:
                    manifest_errors.append(f"{board_id}: manifest dimensions differ from PNG IHDR")
                if hashlib.sha256(asset_path.read_bytes()).hexdigest() == PUBLIC_FIXTURE_SHA256:
                    manifest_errors.append(f"{board_id}: public renderer fixture cannot be release media")
            except (OSError, ValueError, struct.error) as exc:
                manifest_errors.append(f"{board_id}: invalid PNG: {exc}")

    generation_ids = [str(board.get("boardId")) for board in generation_boards or []]
    if set(generation_ids) != set(manifest_ids):
        manifest_errors.append("image generation and manifest board IDs differ")
    generation_run = manifest.get("generationRun") or {}
    if generation.get("automatic") is True and generation_run.get("previewChecked") is not False:
        manifest_errors.append("automatic generation must set previewChecked=false")
    if generation.get("automatic") is False and generation_run.get("previewChecked") is not True:
        manifest_errors.append("interactive generation must set previewChecked=true")
    mode = str(generation_run.get("mode", "")).lower()
    if any(term in mode for term in ("fixture", "placeholder", "smoke")):
        manifest_errors.append("generation mode identifies fixture, placeholder, or smoke media")
    add_check(
        checks,
        "images.manifest",
        not manifest_errors,
        "Board manifest contains validated local model PNGs."
        if not manifest_errors
        else "Board image manifest violates the v1 asset contract.",
        errors=manifest_errors,
    )

    try:
        identity = run_identity_check(
            argparse.Namespace(
                project_dir=project_dir,
                manifest=None,
                board_root=None,
                hyperframes_board_root=None,
                stage="all",
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        identity = {"ok": False, "errors": [str(exc)]}
    add_check(
        checks,
        "images.identity",
        bool(identity.get("ok")),
        "Manifest, D, and HyperFrames board PNGs are identical."
        if identity.get("ok")
        else "Board image identity check failed.",
        errors=identity.get("errors", []),
    )


def check_renderer(
    project_dir: Path,
    checks: list[dict[str, Any]],
    ffprobe: str | None,
    min_duration: float,
    max_duration: float,
    max_delta: float,
) -> None:
    preview = project_dir / "video" / "preview.mp4"
    narration = project_dir / "audio" / "narration.wav"
    timing_path = project_dir / "audio" / "voiceover_timing.json"
    report_path = project_dir / "video" / "renderer_report.json"
    if not preview.is_file() or not narration.is_file() or not timing_path.is_file() or not report_path.is_file():
        return
    report = read_json(report_path, checks, "renderer.report_json")
    timing = read_json(timing_path, checks, "audio.timing_json")
    if not isinstance(report, dict) or not isinstance(timing, dict):
        return

    if not ffprobe:
        add_check(checks, "video.ffprobe", False, "ffprobe is required for release validation.")
        return
    try:
        rendered_duration = probe_duration(ffprobe, preview)
        narration_duration = probe_duration(ffprobe, narration)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        add_check(checks, "video.ffprobe", False, "preview.mp4 could not be probed.", error=str(exc))
        return

    timing_duration = timing.get("totalDuration")
    duration_ok = (
        isinstance(timing_duration, (int, float))
        and min_duration <= rendered_duration <= max_duration
        and min_duration <= narration_duration <= max_duration
        and min_duration <= float(timing_duration) <= max_duration
        and abs(rendered_duration - float(timing_duration)) <= max_delta
        and abs(narration_duration - float(timing_duration)) <= max_delta
    )
    add_check(
        checks,
        "video.duration",
        duration_ok,
        "Rendered and timing durations satisfy the v1 target."
        if duration_ok
        else "Video duration is outside the v1 range or differs from timing.",
        rendered=rendered_duration,
        narration=narration_duration,
        timing=timing_duration,
        allowed=[min_duration, max_duration],
        max_delta=max_delta,
    )

    renderer_ok = report.get("mode") == "multi-board" and report.get("render") == "complete" and report.get("keyframes", {}).get(
        "status"
    ) == "complete"
    validation = report.get("validation") or {}
    renderer_ok = renderer_ok and validation.get("help") == "pass" and validation.get(
        "dryRun"
    ) == "pass"
    hyperframes = report.get("checks")
    renderer_ok = renderer_ok and isinstance(hyperframes, dict) and all(
        (hyperframes.get(name) or {}).get("status") == 0
        for name in ("lint", "validate", "inspect")
    )
    renderer_delta = (report.get("durationCheck") or {}).get("delta")
    renderer_ok = renderer_ok and isinstance(renderer_delta, (int, float)) and renderer_delta <= max_delta
    add_check(
        checks,
        "renderer.complete",
        renderer_ok,
        "Renderer, HyperFrames checks, and keyframe extraction completed."
        if renderer_ok
        else "Renderer or HyperFrames acceptance is incomplete.",
    )


def check_qa_and_keyframes(project_dir: Path, checks: list[dict[str, Any]]) -> None:
    qa_path = project_dir / "sync" / "action_camera_qa_report.json"
    manifest_path = project_dir / "video" / "keyframes" / "keyframe_manifest.json"
    if not qa_path.is_file() or not manifest_path.is_file():
        return
    qa = read_json(qa_path, checks, "qa.report_json")
    keyframes = read_json(manifest_path, checks, "keyframes.manifest_json")
    renderer = read_json(project_dir / "video" / "renderer_report.json", checks, "keyframes.renderer_json")
    action_timing = read_json(project_dir / "sync" / "action_timing.json", checks, "keyframes.action_timing_json")
    motion_plan = read_json(
        project_dir / "board_source_for_e" / "combined_motion_plan.json",
        checks,
        "keyframes.motion_plan_json",
    )
    if (
        not isinstance(qa, dict)
        or not isinstance(keyframes, list)
        or not isinstance(renderer, dict)
        or not isinstance(action_timing, dict)
        or not isinstance(motion_plan, dict)
    ):
        return
    summary = qa.get("summary") or {}
    artifacts = summary.get("keyframeArtifacts") or {}
    qa_ok = (
        summary.get("status") == "pass"
        and isinstance(summary.get("actionCount"), int)
        and summary.get("actionCount") > 0
        and all(
            summary.get(field) == 0
            for field in (
                "fallbackActions",
                "rhythmCompressedActions",
                "bboxIssues",
                "cameraWarnings",
                "keyframeIssues",
            )
        )
    )
    qa_ok = qa_ok and all(
        artifacts.get(field) is True
        for field in ("manifest", "contactSheetStart", "contactSheetDone")
    )
    add_check(
        checks,
        "qa.action_camera",
        qa_ok,
        "Action/camera QA passed without blocking issues."
        if qa_ok
        else "Action/camera QA contains blocking issues.",
        summary=summary,
    )

    frame_errors: list[str] = []
    if not keyframes:
        frame_errors.append("keyframe manifest is empty")
    for row in keyframes:
        for field in ("boardId", "segment", "annotation", "type", "element", "drawStart", "drawDone"):
            if row.get(field) is None or row.get(field) == "":
                frame_errors.append(f"row {row.get('index')}: missing {field}")
        draw_start = row.get("drawStart")
        draw_done = row.get("drawDone")
        if not (
            isinstance(draw_start, (int, float))
            and isinstance(draw_done, (int, float))
            and 0 <= draw_start <= draw_done
            and draw_done <= float(renderer.get("totalDuration", -1)) + 0.1
        ):
            frame_errors.append(f"row {row.get('index')}: invalid draw interval")
        for field in ("startFrame", "doneFrame"):
            value = row.get(field)
            if not isinstance(value, str) or not value:
                frame_errors.append(f"row {row.get('index')}: missing {field}")
                continue
            path = resolve_output_path(value, project_dir, manifest_path.parent)
            if not inside_project(path, project_dir):
                frame_errors.append(f"row {row.get('index')}: {field} escapes project")
            elif not path.is_file():
                frame_errors.append(f"row {row.get('index')}: missing {field} file")
    motion_action_count = sum(
        len(segment.get("actions") or []) for segment in motion_plan.get("segments") or []
    )
    expected_counts = {
        "qa": summary.get("actionCount"),
        "renderer": (renderer.get("keyframes") or {}).get("actionCount"),
        "actionTiming": len(action_timing.get("actions") or []),
        "motionPlan": motion_action_count,
    }
    if any(count != len(keyframes) for count in expected_counts.values()):
        frame_errors.append("action counts disagree with keyframe manifest")
    add_check(
        checks,
        "keyframes.complete",
        not frame_errors,
        "Every action has start and done keyframes."
        if not frame_errors
        else "Keyframe acceptance is incomplete.",
        errors=frame_errors,
        counts=expected_counts,
    )


def check_integration_report(project_dir: Path, checks: list[dict[str, Any]]) -> None:
    path = project_dir / "integration_report.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = bool(text.strip())
    add_check(
        checks,
        "report.integration",
        passed,
        "Integration report records acceptance results."
        if passed
        else "Integration report is empty.",
    )


def check_board_contract(project_dir: Path, checks: list[dict[str, Any]]) -> None:
    manifest_path = project_dir / "board_asset_manifest.json"
    board_index_path = project_dir / "board_source_for_e" / "board_index.json"
    renderer_path = project_dir / "video" / "renderer_report.json"
    if not manifest_path.is_file() or not board_index_path.is_file() or not renderer_path.is_file():
        return
    manifest = read_json(manifest_path, checks, "boards.manifest_json")
    board_index = read_json(board_index_path, checks, "boards.index_json")
    renderer = read_json(renderer_path, checks, "boards.renderer_json")
    if not all(isinstance(item, dict) for item in (manifest, board_index, renderer)):
        return
    manifest_ids = {str(board.get("boardId")) for board in manifest.get("boards") or []}
    index_ids = {
        str(board.get("boardId") or board.get("id")) for board in board_index.get("boards") or []
    }
    renderer_ids = {str(board) for board in renderer.get("boards") or []}
    errors: list[str] = []
    if not manifest_ids or manifest_ids != index_ids or manifest_ids != renderer_ids:
        errors.append("manifest, D board index, and renderer board IDs differ")
    for board_id in manifest_ids:
        for name in ("board_manifest.json", "annotation_manifest.json", "motion_plan.json", "board.png"):
            path = project_dir / "board_source_for_e" / board_id / name
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"{board_id}: missing or empty {name}")
    add_check(
        checks,
        "boards.contract",
        not errors,
        "Board IDs and D package files agree across stages."
        if not errors
        else "Board package contract is incomplete.",
        errors=errors,
    )


def check_forbidden_prefixes(
    project_dir: Path, checks: list[dict[str, Any]], prefixes: list[str]
) -> None:
    if not prefixes:
        return
    matches: list[str] = []
    for path in project_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.name in {"v1_release_acceptance.json", "v1_release_acceptance.md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for prefix in prefixes:
            if prefix and prefix in text:
                matches.append(f"{path.relative_to(project_dir)} contains {prefix}")
    add_check(
        checks,
        "paths.forbidden_prefix",
        not matches,
        "No obsolete source prefix appears in text outputs."
        if not matches
        else "Obsolete source prefixes remain in project outputs.",
        matches=matches,
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    project_dir = args.project_dir.expanduser().resolve()
    checks: list[dict[str, Any]] = []
    if not project_dir.is_dir():
        add_check(checks, "project.directory", False, "Project directory does not exist.")
    else:
        add_check(checks, "project.directory", True, "Project directory exists.")
        check_required_files(project_dir, checks)
        check_images(project_dir, checks)
        ffprobe = args.ffprobe or shutil.which("ffprobe")
        check_renderer(
            project_dir,
            checks,
            ffprobe,
            args.min_duration,
            args.max_duration,
            args.max_duration_delta,
        )
        check_qa_and_keyframes(project_dir, checks)
        check_board_contract(project_dir, checks)
        check_integration_report(project_dir, checks)
        check_forbidden_prefixes(project_dir, checks, args.forbid_prefix)
    return {
        "schemaVersion": 1,
        "status": "PASS" if checks and all(item["status"] == "PASS" for item in checks) else "FAIL",
        "projectDir": str(project_dir),
        "checks": checks,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# V1 Release Acceptance",
        "",
        f"Status: **{report['status']}**",
        "",
        f"Project: `{report['projectDir']}`",
        "",
        "## Checks",
        "",
    ]
    for item in report["checks"]:
        lines.append(f"- {item['status']} `{item['id']}` — {item['message']}")
    return "\n".join(lines) + "\n"


def write_reports(project_dir: Path, report: dict[str, Any]) -> None:
    if not project_dir.is_dir():
        return
    (project_dir / "v1_release_acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (project_dir / "v1_release_acceptance.md").write_text(
        markdown_report(report), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    report = build_report(args)
    write_reports(args.project_dir.expanduser().resolve(), report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown_report(report), end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
