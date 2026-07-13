#!/usr/bin/env python3
"""End-to-end smoke test for the whiteboard-video pipeline.

Usage:
    python3 scripts/smoke_test.py --project-dir /tmp/test-run --fast
    python3 scripts/smoke_test.py --project-dir /tmp/test-run --real
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERER = (
    REPO_ROOT
    / "whiteboard-infographic-video-renderer"
    / "scripts"
    / "render_multi_board_project.mjs"
)
EXAMPLE_INPUT = REPO_ROOT / "whiteboard-infographic-video-renderer" / "examples" / "input"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a minimal end-to-end whiteboard-video pipeline smoke test."
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        required=True,
        help="Directory where the smoke-test project will be built and rendered.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip real TTS and MP4 rendering; verify pipeline structure only.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run a small real render with silent audio and low quality.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the project directory after the test.",
    )
    return parser.parse_args()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(command: list[str], cwd: Path, timeout: float = 300.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )


def make_silent_audio(path: Path, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            str(duration),
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def make_fixture(project_dir: Path) -> dict[str, Any]:
    project_dir.mkdir(parents=True, exist_ok=True)

    source = {
        "topic": "Smoke test video",
        "style": "IP孵化/商业认知/AI认知类短视频",
        "targetDurationSec": 8.0,
        "estimatedDurationSec": 8.0,
        "segments": [
            {
                "id": "hook",
                "role": "hook",
                "text": "第一句口播用于冒烟测试。",
                "caption": "第一句口播用于冒烟测试。",
                "visualIntent": "建立测试画面",
                "spokenAnchors": ["冒烟测试"],
                "boardId": "board-01",
                "targetElement": "title",
                "pauseAfter": 0.12,
                "actions": [
                    {
                        "type": "underline",
                        "element": "title",
                        "annotation": "underline_title",
                        "spokenAnchor": "冒烟测试",
                        "anchorRatio": 0.55,
                        "duration": 0.72,
                    }
                ],
            },
            {
                "id": "method",
                "role": "method",
                "text": "第二句口播验证结构完整性。",
                "caption": "第二句口播验证结构完整性。",
                "visualIntent": "验证 pipeline 产物",
                "spokenAnchors": ["结构完整性"],
                "boardId": "board-01",
                "targetElement": "method",
                "pauseAfter": 0,
                "actions": [
                    {
                        "type": "box",
                        "element": "method",
                        "annotation": "box_method",
                        "spokenAnchor": "结构完整性",
                        "anchorRatio": 0.32,
                        "duration": 0.8,
                    }
                ],
            },
        ],
    }

    manifest = {
        "canvas": {"width": 2000, "height": 1300},
        "source_image": "board.png",
        "elements": [
            {
                "id": "title",
                "kind": "title",
                "text": "冒烟测试标题",
                "bbox": [520, 220, 760, 92],
                "camera": {"x": 900, "y": 320, "scale": 0.95},
                "annotations": {
                    "underline_title": {
                        "type": "underline",
                        "underlineStart": [530, 334],
                        "underlineEnd": [1280, 330],
                        "controlPoints": [[680, 348], [920, 316], [1120, 342]],
                        "cursorStart": [530, 318],
                        "cursorEnd": [1280, 314],
                    }
                },
            },
            {
                "id": "method",
                "kind": "method_box",
                "text": "结构完整性检查",
                "bbox": [520, 640, 960, 160],
                "camera": {"x": 1000, "y": 720, "scale": 0.9},
                "annotations": {
                    "box_method": {
                        "type": "box",
                        "boxBounds": [500, 620, 1020, 200],
                        "cornerRadius": 28,
                        "cursorStart": [500, 620],
                        "cursorEnd": [1520, 800],
                    }
                },
            },
        ],
    }

    annotations = []
    for element in manifest["elements"]:
        for annotation_id, annotation in element.get("annotations", {}).items():
            annotations.append(
                {
                    "id": annotation_id,
                    "element": element["id"],
                    "bbox": element["bbox"],
                    **annotation,
                }
            )
    annotation_manifest = {
        "canvas": manifest["canvas"],
        "source_image": "board.png",
        "coordinate_system": "board-image-pixels",
        "annotations": annotations,
    }

    motion_plan = {
        "sync_level": "voiceover-segment-action",
        "composition": {"width": 1920, "height": 1080, "duration": 8},
        "overview_camera": {"x": 1000, "y": 650, "scale": 0.72},
        "segments": [
            {
                "id": "hook",
                "start": 0,
                "speechEnd": 3.5,
                "end": 3.62,
                "caption": "第一句口播用于冒烟测试。",
                "target": "title",
                "boardId": "board-01",
                "camera": {"x": 900, "y": 320, "scale": 0.95},
                "actions": [
                    {
                        "type": "underline",
                        "element": "title",
                        "annotation": "underline_title",
                        "spokenAnchor": "冒烟测试",
                        "offset": 1.8,
                        "duration": 0.72,
                    }
                ],
            },
            {
                "id": "method",
                "start": 3.62,
                "speechEnd": 8,
                "end": 8,
                "caption": "第二句口播验证结构完整性。",
                "target": "method",
                "boardId": "board-01",
                "camera": {"x": 1000, "y": 720, "scale": 0.9},
                "actions": [
                    {
                        "type": "box",
                        "element": "method",
                        "annotation": "box_method",
                        "spokenAnchor": "结构完整性",
                        "offset": 1.4,
                        "duration": 0.8,
                    }
                ],
            },
        ],
    }

    board_root = project_dir / "board_source_for_e"
    board_dir = board_root / "board-01"
    board_dir.mkdir(parents=True, exist_ok=True)

    write_json(project_dir / "script" / "voiceover_segments.json", source)
    shutil.copy(EXAMPLE_INPUT / "board" / "board.png", board_dir / "board.png")
    write_json(board_dir / "board_manifest.json", manifest)
    write_json(board_dir / "annotation_manifest.json", annotation_manifest)
    write_json(board_dir / "motion_plan.json", motion_plan)
    write_json(
        board_root / "board_index.json",
        {
            "version": "0.1",
            "boards": [
                {
                    "boardId": "board-01",
                    "path": "board-01",
                    "asset": {"kind": "file", "localPath": "board.png"},
                }
            ],
            "combinedMotionPlan": "combined_motion_plan.json",
        },
    )
    write_json(board_root / "combined_motion_plan.json", motion_plan)

    return source


def run_renderer(project_dir: Path, fast: bool, real: bool) -> dict[str, Any]:
    args = [
        str(RENDERER),
        "--project-dir",
        str(project_dir),
        "--board-root",
        str(project_dir / "board_source_for_e"),
        "--voiceover",
        str(project_dir / "script" / "voiceover_segments.json"),
    ]
    source = json.loads(
        (project_dir / "script" / "voiceover_segments.json").read_text(encoding="utf-8")
    )
    if fast:
        audio_dir = project_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        make_silent_audio(audio_dir / "narration.wav", 8.0)
        timing = {
            "engine": "fixture",
            "voice": {
                "name": "zh-CN-YunxiNeural",
                "rate": "+14%",
                "pitch": "+0Hz",
                "volume": "+0%",
            },
            "totalDuration": 8.0,
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "voiceover_segments.json",
            "output": "audio/narration.wav",
            "segments": [
                {
                    "id": "hook",
                    "text": "第一句口播用于冒烟测试。",
                    "caption": "第一句口播用于冒烟测试。",
                    "start": 0,
                    "speechEnd": 3.5,
                    "end": 3.62,
                    "speechDuration": 3.5,
                    "media": {"wav": "audio/narration.wav", "subtitles": "audio/segments/01-hook.vtt"},
                    "actions": source["segments"][0]["actions"],
                },
                {
                    "id": "method",
                    "text": "第二句口播验证结构完整性。",
                    "caption": "第二句口播验证结构完整性。",
                    "start": 3.62,
                    "speechEnd": 8,
                    "end": 8,
                    "speechDuration": 4.38,
                    "media": {"wav": "audio/narration.wav", "subtitles": "audio/segments/02-method.vtt"},
                    "actions": source["segments"][1]["actions"],
                },
            ],
        }
        write_json(audio_dir / "voiceover_timing.json", timing)
        (audio_dir / "segments").mkdir(parents=True, exist_ok=True)
        (audio_dir / "segments" / "01-hook.vtt").write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:03.500\n第一句口播用于冒烟测试。\n",
            encoding="utf-8",
        )
        (audio_dir / "segments" / "02-method.vtt").write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:04.380\n第二句口播验证结构完整性。\n",
            encoding="utf-8",
        )
        args.extend(["--skip-tts", "--skip-checks", "--skip-render"])
    elif real:
        audio_dir = project_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        make_silent_audio(audio_dir / "narration.wav", 8.0)
        timing = {
            "engine": "fixture",
            "voice": {
                "name": "zh-CN-YunxiNeural",
                "rate": "+14%",
                "pitch": "+0Hz",
                "volume": "+0%",
            },
            "totalDuration": 8.0,
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "voiceover_segments.json",
            "output": "audio/narration.wav",
            "segments": [
                {
                    "id": "hook",
                    "start": 0,
                    "speechEnd": 3.5,
                    "end": 3.62,
                    "speechDuration": 3.5,
                    "media": {"wav": "audio/narration.wav"},
                },
                {
                    "id": "method",
                    "start": 3.62,
                    "speechEnd": 8,
                    "end": 8,
                    "speechDuration": 4.38,
                    "media": {"wav": "audio/narration.wav"},
                },
            ],
        }
        write_json(audio_dir / "voiceover_timing.json", timing)
        args.extend(["--skip-tts", "--quality", "draft", "--fps", "8"])

    start = time.time()
    result = run_command(["node", *args], cwd=REPO_ROOT)
    duration = time.time() - start

    if result.returncode != 0:
        raise RuntimeError(
            f"renderer failed with exit {result.returncode}\n{result.stdout}\n{result.stderr}"
        )

    return {
        "command": " ".join(args),
        "durationSec": round(duration, 3),
        "returncode": result.returncode,
    }


def verify_outputs(project_dir: Path, fast: bool, real: bool) -> dict[str, Any]:
    required: list[tuple[str, str]] = [
        ("audio/narration.wav", "audio"),
        ("audio/voiceover_timing.json", "audio"),
        ("audio/word_timing.json", "audio"),
        ("audio/captions.srt", "audio"),
        ("sync/action_timing.json", "sync"),
        ("sync/camera_plan.json", "sync"),
        ("sync/action_camera_qa_report.json", "sync"),
        ("sync/action_camera_qa_report.md", "sync"),
        ("board/combined_motion_plan.json", "board"),
        ("video/hyperframes/index.html", "video"),
        ("video/hyperframes/package.json", "video"),
        ("video/hyperframes/hyperframes.json", "video"),
        ("video/renderer_report.json", "video"),
    ]
    if not fast:
        required.extend(
            [
                ("video/preview.mp4", "video"),
                ("video/keyframes/keyframe_manifest.json", "video"),
                ("video/keyframes/contact_sheet_start.jpg", "video"),
                ("video/keyframes/contact_sheet_done.jpg", "video"),
            ]
        )

    missing: list[str] = []
    files: list[str] = []
    for relative, stage in required:
        path = project_dir / relative
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(relative)
        else:
            files.append(relative)

    return {
        "allPresent": not missing,
        "missing": missing,
        "files": files,
    }


def main() -> int:
    args = parse_args()
    if args.fast and args.real:
        print("ERROR: --fast and --real are mutually exclusive", file=sys.stderr)
        return 2
    mode = "real" if args.real else "fast"

    project_dir = args.project_dir.expanduser().resolve()
    report_path = project_dir / "smoke_test_report.json"
    start_time = time.time()

    stages: list[dict[str, Any]] = []
    overall = "PASS"
    error_message: str | None = None
    renderer_info: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None

    try:
        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)

        stages.append(
            {
                "name": "fixture",
                "status": "RUNNING",
                "startTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )
        make_fixture(project_dir)
        source = json.loads(
            (project_dir / "script" / "voiceover_segments.json").read_text(encoding="utf-8")
        )
        stages[-1]["status"] = "PASS"
        stages[-1]["outputs"] = ["script/voiceover_segments.json", "board_source_for_e/"]

        stages.append(
            {
                "name": "E-render",
                "status": "RUNNING",
                "startTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )
        renderer_info = run_renderer(project_dir, fast=args.fast, real=args.real)
        stages[-1]["status"] = "PASS"
        stages[-1]["durationSec"] = renderer_info["durationSec"]

        stages.append(
            {
                "name": "verify",
                "status": "RUNNING",
                "startTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )
        outputs = verify_outputs(project_dir, fast=args.fast, real=args.real)
        stages[-1]["status"] = "PASS" if outputs["allPresent"] else "FAIL"
        stages[-1]["outputs"] = outputs["files"]
        if not outputs["allPresent"]:
            overall = "FAIL"
            error_message = f"Missing outputs: {outputs['missing']}"
    except Exception as exc:  # noqa: BLE001
        overall = "FAIL"
        error_message = str(exc)
        if stages and stages[-1].get("status") == "RUNNING":
            stages[-1]["status"] = "FAIL"
            stages[-1]["error"] = error_message

    total_duration = round(time.time() - start_time, 3)

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "mode": mode,
        "overall": overall,
        "projectDir": str(project_dir),
        "totalDurationSec": total_duration,
        "startedAt": datetime.datetime.fromtimestamp(
            start_time, tz=datetime.timezone.utc
        ).isoformat(),
        "completedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stages": stages,
        "outputs": outputs,
        "renderer": renderer_info,
    }
    if error_message:
        report["error"] = error_message

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if overall == "PASS":
        print(f"[{overall}] smoke test {mode} completed in {total_duration}s")
        print(f"report: {report_path}")
        if not args.keep:
            shutil.rmtree(project_dir)
        return 0

    print(f"[{overall}] smoke test {mode} failed: {error_message}", file=sys.stderr)
    print(f"report: {report_path}", file=sys.stderr)
    print(f"project dir retained: {project_dir}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
