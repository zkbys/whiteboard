from __future__ import annotations

import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = (
    REPO_ROOT
    / "whiteboard-infographic-pipeline-orchestrator"
    / "scripts"
    / "validate_release_candidate.py"
)


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def make_png(value: int = 255, width: int = 512, height: int = 512) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    row = b"\x00" + (bytes([value]) * width)
    pixels = zlib.compress(row * height, level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", pixels)
        + png_chunk(b"IEND", b"")
    )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ReleaseAcceptanceTests(unittest.TestCase):
    def make_ffprobe(self, root: Path) -> Path:
        executable = root / "fake ffprobe"
        executable.write_text(
            """#!/usr/bin/env python3
import json
import os
print(json.dumps({'format': {'duration': os.environ.get('FAKE_DURATION', '42.0')}}))
""",
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def make_project(self, root: Path) -> Path:
        project = root / "project"
        board_id = "board-01"
        png = make_png()
        text_files = {
            "script/visual_beats.json": "[]\n",
            "audio/captions.srt": "1\n00:00:00,000 --> 00:00:01,000\n测试\n",
            "sync/action_camera_qa_report.md": "# QA\n\nPASS\n",
            "video/hyperframes/index.html": "<!doctype html><title>whiteboard</title>\n",
            "video/hyperframes/DESIGN.md": "# Design\n",
            "video/hyperframes/hyperframes.json": "{}\n",
            "video/hyperframes/package.json": "{}\n",
            "integration_report.md": "# Integration report\n\nAll release checks passed.\n",
        }
        for relative, text in text_files.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        write_json(project / "script/voiceover_segments.json", {"segments": []})
        write_json(
            project / "infographic/infographic_plan.json",
            {"boards": [{"id": board_id, "title": "Board"}]},
        )
        write_json(
            project / "image_generation_report.json",
            {
                "status": "complete",
                "providerResolved": "command",
                "automatic": True,
                "boards": [{"boardId": board_id, "status": "generated"}],
                "manifestPath": "board_asset_manifest.json",
            },
        )
        write_json(
            project / "board_asset_manifest.json",
            {
                "generationRun": {"mode": "auto:command", "previewChecked": False},
                "boards": [
                    {
                        "boardId": board_id,
                        "asset": {
                            "kind": "file",
                            "uri": f"images/{board_id}.model-generated.png",
                            "width": 512,
                            "height": 512,
                        },
                    }
                ],
            },
        )
        write_json(
            project / "board_source_for_e/board_index.json",
            {"boards": [{"boardId": board_id}]},
        )
        write_json(
            project / "board_source_for_e/combined_motion_plan.json",
            {
                "segments": [
                    {
                        "id": "seg-01",
                        "boardId": board_id,
                        "actions": [{"annotation": "circle_title"}],
                    }
                ]
            },
        )
        for name in ("board_manifest.json", "annotation_manifest.json", "motion_plan.json"):
            write_json(project / "board_source_for_e" / board_id / name, {"boardId": board_id})

        for relative in (
            f"images/{board_id}.model-generated.png",
            f"board_source_for_e/{board_id}/board.png",
            f"video/hyperframes/assets/boards/{board_id}/board.png",
        ):
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png)

        audio = project / "audio/narration.wav"
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"fixture wav")
        write_json(project / "audio/voiceover_timing.json", {"totalDuration": 42.0})
        write_json(project / "audio/word_timing.json", {"words": []})
        write_json(
            project / "sync/action_timing.json",
            {"actions": [{"annotation": "circle_title"}]},
        )
        write_json(project / "sync/camera_plan.json", {"segments": []})
        write_json(
            project / "sync/action_camera_qa_report.json",
            {
                "summary": {
                    "status": "pass",
                    "actionCount": 1,
                    "fallbackActions": 0,
                    "rhythmCompressedActions": 0,
                    "bboxIssues": 0,
                    "cameraWarnings": 0,
                    "keyframeIssues": 0,
                    "keyframeArtifacts": {
                        "manifest": True,
                        "contactSheetStart": True,
                        "contactSheetDone": True,
                    },
                }
            },
        )

        preview = project / "video/preview.mp4"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(b"fixture mp4")
        keyframe_dir = project / "video/keyframes"
        keyframe_dir.mkdir(parents=True)
        for name in ("start.jpg", "done.jpg", "contact_sheet_start.jpg", "contact_sheet_done.jpg"):
            (keyframe_dir / name).write_bytes(b"fixture jpg")
        write_json(
            keyframe_dir / "keyframe_manifest.json",
            [
                {
                    "index": 1,
                    "boardId": board_id,
                    "segment": "seg-01",
                    "annotation": "circle_title",
                    "type": "circle",
                    "element": "title",
                    "drawStart": 10.0,
                    "drawDone": 11.0,
                    "startFrame": "video/keyframes/start.jpg",
                    "doneFrame": "video/keyframes/done.jpg",
                }
            ],
        )
        write_json(
            project / "video/renderer_report.json",
            {
                "mode": "multi-board",
                "totalDuration": 42.0,
                "boards": [board_id],
                "render": "complete",
                "keyframes": {"status": "complete", "actionCount": 1},
                "validation": {"help": "pass", "dryRun": "pass"},
                "checks": {
                    "lint": {"status": 0},
                    "validate": {"status": 0},
                    "inspect": {"status": 0},
                },
                "durationCheck": {"renderedDuration": 42.0, "timingDuration": 42.0, "delta": 0.0},
            },
        )
        return project

    def run_validator(
        self,
        project: Path,
        ffprobe: Path,
        *,
        expected: int = 0,
        duration: str = "42.0",
        extra: tuple[str, ...] = (),
    ) -> dict[str, object]:
        env = os.environ.copy()
        env["FAKE_DURATION"] = duration
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--project-dir",
                str(project),
                "--ffprobe",
                str(ffprobe),
                "--json",
                *extra,
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return json.loads(result.stdout)

    def test_healthy_release_candidate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.run_validator(self.make_project(root), self.make_ffprobe(root))
            self.assertEqual(report["status"], "PASS")
            self.assertTrue((root / "project/v1_release_acceptance.md").is_file())

    def test_missing_preview_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root)
            (project / "video/preview.mp4").unlink()
            report = self.run_validator(project, self.make_ffprobe(root), expected=1)
            self.assertEqual(report["status"], "FAIL")

    def test_out_of_range_duration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.run_validator(
                self.make_project(root), self.make_ffprobe(root), expected=1, duration="29.9"
            )
            self.assertEqual(report["status"], "FAIL")

    def test_qa_failure_and_asset_mismatch_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root)
            qa_path = project / "sync/action_camera_qa_report.json"
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
            qa["summary"].update({"status": "fail", "bboxIssues": 1})
            write_json(qa_path, qa)
            (project / "board_source_for_e/board-01/board.png").write_bytes(make_png(value=0))
            report = self.run_validator(project, self.make_ffprobe(root), expected=1)
            failed = {item["id"] for item in report["checks"] if item["status"] == "FAIL"}
            self.assertIn("qa.action_camera", failed)
            self.assertIn("images.identity", failed)

    def test_forbidden_source_prefix_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root)
            prefix = "/old/source/checkout"
            (project / "integration_report.md").write_text(prefix, encoding="utf-8")
            report = self.run_validator(
                project,
                self.make_ffprobe(root),
                expected=1,
                extra=("--forbid-prefix", prefix),
            )
            failed = {item["id"] for item in report["checks"] if item["status"] == "FAIL"}
            self.assertIn("paths.forbidden_prefix", failed)

    def test_incomplete_provider_and_renderer_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root)
            generation_path = project / "image_generation_report.json"
            generation = json.loads(generation_path.read_text(encoding="utf-8"))
            generation["status"] = "failed"
            write_json(generation_path, generation)
            renderer_path = project / "video/renderer_report.json"
            renderer = json.loads(renderer_path.read_text(encoding="utf-8"))
            renderer["render"] = "skipped"
            write_json(renderer_path, renderer)
            report = self.run_validator(project, self.make_ffprobe(root), expected=1)
            failed = {item["id"] for item in report["checks"] if item["status"] == "FAIL"}
            self.assertIn("images.generation", failed)
            self.assertIn("renderer.complete", failed)


if __name__ == "__main__":
    unittest.main()
