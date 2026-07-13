"""Unit tests for the whiteboard auto-calibration flow."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTO_CALIBRATE = (
    REPO_ROOT
    / "hand-drawn-infographic-video-board"
    / "scripts"
    / "auto_calibrate.py"
)
CALIBRATION_TOOL = (
    REPO_ROOT
    / "hand-drawn-infographic-video-board"
    / "scripts"
    / "create_calibration_tool.py"
)


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def make_png(width: int = 1536, height: int = 864, value: int = 250) -> bytes:
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


def make_project(root: Path, *, partial: bool = False) -> Path:
    project = root / "project"
    board_id = "board-01"
    (project / "images").mkdir(parents=True, exist_ok=True)
    (project / "infographic" / "board_specs").mkdir(parents=True, exist_ok=True)
    (project / "script").mkdir(parents=True, exist_ok=True)

    (project / f"images/{board_id}.model-generated.png").write_bytes(make_png())

    write_json(
        project / "infographic" / "infographic_plan.json",
        {
            "boards": [
                {
                    "id": board_id,
                    "title": "Board title",
                    "boardSpecPath": "infographic/board_specs/board-01.board_spec.json",
                }
            ]
        },
    )
    write_json(
        project / "infographic" / "board_specs" / f"{board_id}.board_spec.json",
        {
            "id": board_id,
            "title": "AI 工具越多，普通人反而越低效",
            "canvas": {"width": 1536, "height": 864},
            "keyObjects": [
                {"id": "title", "label": "AI 工具越多，普通人反而越低效", "role": "title"},
                {"id": "judgment", "label": "判断流程", "role": "mechanism"},
            ],
        },
    )
    write_json(
        project / "script" / "voiceover_segments.json",
        {
            "segments": [
                {
                    "id": "seg-01",
                    "boardId": board_id,
                    "targetElement": "title",
                    "actions": [{"element": "title"}],
                },
                {
                    "id": "seg-02",
                    "boardId": board_id,
                    "targetElement": "judgment",
                    "actions": [{"element": "judgment"}],
                },
            ]
        },
    )
    write_json(
        project / "board_asset_manifest.json",
        {
            "boards": [
                {
                    "boardId": board_id,
                    "asset": {
                        "kind": "file",
                        "uri": f"images/{board_id}.model-generated.png",
                        "width": 1536,
                        "height": 864,
                    },
                }
            ]
        },
    )

    if partial:
        # Voiceover references an element absent from the spec to trigger partial status.
        voiceover = json.loads((project / "script" / "voiceover_segments.json").read_text(encoding="utf-8"))
        voiceover["segments"].append(
            {"id": "seg-03", "boardId": board_id, "targetElement": "missing", "actions": []}
        )
        write_json(project / "script" / "voiceover_segments.json", voiceover)

    return project


def run_auto_calibrate(project: Path, *extra: str) -> tuple[int, dict[str, object]]:
    env = os.environ.copy()
    env["WHITEBOARD_AUTO_CALIBRATE_MOCK"] = "1"
    result = subprocess.run(
        [sys.executable, str(AUTO_CALIBRATE), "--project-dir", str(project), "--json", *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    report = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, report


class AutoCalibrationTests(unittest.TestCase):
    def test_mock_backend_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = make_project(Path(tmpdir))
            code, report = run_auto_calibrate(project, "--provider", "mock")
            self.assertEqual(code, 0)
            self.assertEqual(report.get("status"), "complete")
            self.assertEqual(report["boards"][0]["matchedCount"], 2)

            cal_path = project / "calibration" / "board-01.element_bboxes.json"
            self.assertTrue(cal_path.exists())
            cal = json.loads(cal_path.read_text(encoding="utf-8"))
            self.assertEqual(cal["boardId"], "board-01")
            self.assertIn("elements", cal)
            ids = {el["id"] for el in cal["elements"]}
            self.assertEqual(ids, {"title", "judgment"})
            for element in cal["elements"]:
                self.assertIn("bbox", element)
                self.assertIn("annotationTargetBbox", element)
                self.assertIn("camera", element)
                self.assertIn("cursor", element)

    def test_partial_coverage_triggers_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = make_project(Path(tmpdir), partial=True)
            code, report = run_auto_calibrate(
                project, "--provider", "mock", "--write-tool-on-partial"
            )
            self.assertEqual(code, 3)
            self.assertEqual(report.get("status"), "partial")
            review_ids = {item["id"] for item in report["boards"][0].get("review", [])}
            self.assertIn("missing", review_ids)
            self.assertTrue((project / "calibration_tool" / "index.html").exists())

    def test_vlm_backend_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = make_project(Path(tmpdir))
            code, report = run_auto_calibrate(project, "--provider", "vlm", "--dry-run")
            self.assertEqual(code, 0)
            self.assertTrue(report.get("dryRun"))
            self.assertEqual(report["vlm"]["model"], "gpt-4o")

    def test_calibration_report_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = make_project(Path(tmpdir))
            code, report = run_auto_calibrate(project, "--provider", "mock")
            self.assertEqual(code, 0)
            self.assertEqual(report.get("schemaVersion"), 1)
            self.assertIn("provider", report)
            self.assertIn("boards", report)
            report_path = project / "calibration" / "auto_calibration_report.json"
            self.assertTrue(report_path.exists())
            on_disk = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["status"], "complete")

    def test_calibration_tool_prefill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = make_project(Path(tmpdir))
            run_auto_calibrate(project, "--provider", "mock")
            result = subprocess.run(
                [
                    sys.executable,
                    str(CALIBRATION_TOOL),
                    "--project",
                    str(project),
                    "--prefill-from",
                    str(project / "calibration" / "auto_calibration_report.json"),
                    "--overwrite",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["status"], "PASS")
            self.assertTrue((Path(output["index"])).exists())


if __name__ == "__main__":
    unittest.main()
