from __future__ import annotations

import base64
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = (
    REPO_ROOT
    / "whiteboard-infographic-pipeline-orchestrator"
    / "scripts"
    / "generate_board_images.py"
)
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def make_png(width: int = 1536, height: int = 1024) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    row = b"\x00" + (b"\xff" * width)
    pixels = zlib.compress(row * height, level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", pixels)
        + png_chunk(b"IEND", b"")
    )


class ImageProviderTests(unittest.TestCase):
    def make_project(self, root: Path, boards: int = 2) -> Path:
        project = root / "project"
        (project / "infographic").mkdir(parents=True)
        (project / "imagegen_prompts").mkdir()
        (project / "creator_outputs").mkdir()
        plan_boards = []
        for index in range(1, boards + 1):
            board_id = f"board-{index:02d}"
            plan_boards.append({"id": board_id, "title": f"Board {index}"})
            (project / "imagegen_prompts" / f"{board_id}.imagegen_prompt.txt").write_text(
                f"A hand-drawn whiteboard infographic for {board_id}.", encoding="utf-8"
            )
            (project / "creator_outputs" / f"{board_id}.creator_output.md").write_text(
                f"# {board_id}\n", encoding="utf-8"
            )
        (project / "infographic" / "infographic_plan.json").write_text(
            json.dumps({"boards": plan_boards}), encoding="utf-8"
        )
        return project

    def run_generator(
        self,
        project: Path,
        *args: object,
        expected: int = 0,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--project-dir", str(project), *map(str, args)],
            cwd=REPO_ROOT,
            env=env or os.environ.copy(),
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
        return result

    def test_interactive_provider_emits_exact_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_generator(project, "--provider", "interactive", expected=3)
            self.assertIn("HANDOFF_REQUIRED", result.stdout)
            report = json.loads(
                (project / "image_generation_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "handoff_required")
            self.assertFalse(report["automatic"])
            self.assertEqual(
                [board["status"] for board in report["boards"]],
                ["manual_save_required", "manual_save_required"],
            )
            self.assertEqual(
                report["boards"][0]["outputPath"],
                "images/board-01.model-generated.png",
            )
            self.assertFalse((project / "board_asset_manifest.json").exists())

    def test_api_key_alone_does_not_select_a_billable_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary), boards=1)
            env = os.environ.copy()
            env["OPENAI_API_KEY"] = "key-must-not-select-provider"
            env.pop("WHITEBOARD_IMAGE_PROVIDER", None)
            env.pop("WHITEBOARD_IMAGE_COMMAND", None)

            self.run_generator(project, "--provider", "auto", env=env, expected=3)

            report_text = (project / "image_generation_report.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("key-must-not-select-provider", report_text)
            report = json.loads(report_text)
            self.assertEqual(report["providerResolved"], "interactive")
            self.assertFalse(report["automatic"])

    def test_command_provider_generates_manifest_and_reuses_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root)
            helper = root / "image provider"
            helper.write_text(
                """#!/usr/bin/env python3
import argparse
import base64
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--prompt-file')
parser.add_argument('--output-file')
parser.add_argument('--board-id')
args = parser.parse_args()
Path(args.output_file).write_bytes(base64.b64decode(os.environ['FIXTURE_PNG_B64']))
counter = Path(os.environ['COMMAND_COUNTER'])
count = int(counter.read_text() or '0') if counter.exists() else 0
counter.write_text(str(count + 1))
""",
                encoding="utf-8",
            )
            helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
            counter = root / "counter.txt"
            env = os.environ.copy()
            env["FIXTURE_PNG_B64"] = base64.b64encode(make_png()).decode("ascii")
            env["COMMAND_COUNTER"] = str(counter)

            self.run_generator(
                project,
                "--provider",
                "command",
                "--command",
                helper,
                env=env,
            )
            self.assertEqual(counter.read_text(encoding="utf-8"), "2")
            manifest = json.loads(
                (project / "board_asset_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["generationRun"]["mode"], "auto:command")
            self.assertFalse(manifest["generationRun"]["previewChecked"])

            first_mtime = (
                project / "images" / "board-01.model-generated.png"
            ).stat().st_mtime_ns
            self.run_generator(
                project,
                "--provider",
                "command",
                "--command",
                helper,
                env=env,
            )
            self.assertEqual(counter.read_text(encoding="utf-8"), "2")
            self.assertEqual(
                first_mtime,
                (project / "images" / "board-01.model-generated.png").stat().st_mtime_ns,
            )
            report = json.loads(
                (project / "image_generation_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [board["status"] for board in report["boards"]], ["reused", "reused"]
            )

    def test_openai_provider_uses_base64_response_without_leaking_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root, boards=1)
            png = make_png()
            requests: list[dict[str, object]] = []

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    requests.append(
                        {
                            "path": self.path,
                            "authorization": self.headers.get("Authorization"),
                            "payload": payload,
                        }
                    )
                    response = json.dumps(
                        {
                            "data": [
                                {"b64_json": base64.b64encode(png).decode("ascii")}
                            ],
                            "usage": {"total_tokens": 123},
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

                def log_message(self, _format: str, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = os.environ.copy()
                env["OPENAI_API_KEY"] = "test-secret-key"
                self.run_generator(
                    project,
                    "--provider",
                    "openai",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}/v1",
                    env=env,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["path"], "/v1/images/generations")
            self.assertEqual(requests[0]["authorization"], "Bearer test-secret-key")
            payload = requests[0]["payload"]
            self.assertEqual(payload["model"], "gpt-image-2")
            self.assertEqual(payload["size"], "1536x1024")
            self.assertEqual(payload["output_format"], "png")

            report_text = (project / "image_generation_report.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("test-secret-key", report_text)
            report = json.loads(report_text)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["boards"][0]["usage"]["total_tokens"], 123)
            manifest = json.loads(
                (project / "board_asset_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["generationRun"]["mode"], "auto:openai:gpt-image-2")
            self.assertFalse(manifest["generationRun"]["previewChecked"])

    def test_openai_provider_rejects_invalid_base64(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root, boards=1)

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    response = json.dumps({"data": [{"b64_json": "not base64!"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

                def log_message(self, _format: str, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = os.environ.copy()
                env["OPENAI_API_KEY"] = "test-secret-key"
                self.run_generator(
                    project,
                    "--provider",
                    "openai",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}/v1",
                    env=env,
                    expected=2,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            report = json.loads(
                (project / "image_generation_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["boards"][0]["status"], "failed")
            self.assertFalse((project / "board_asset_manifest.json").exists())
            self.assertFalse((project / "images" / "board-01.model-generated.png").exists())

    def test_failure_report_preserves_completed_boards_for_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.make_project(root, boards=2)
            png = make_png()
            request_count = 0

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    nonlocal request_count
                    request_count += 1
                    encoded = (
                        base64.b64encode(png).decode("ascii")
                        if request_count == 1
                        else "not base64!"
                    )
                    response = json.dumps({"data": [{"b64_json": encoded}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

                def log_message(self, _format: str, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = os.environ.copy()
                env["OPENAI_API_KEY"] = "test-secret-key"
                self.run_generator(
                    project,
                    "--provider",
                    "openai",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}/v1",
                    env=env,
                    expected=2,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            report = json.loads(
                (project / "image_generation_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [board["status"] for board in report["boards"]],
                ["generated", "failed"],
            )
            self.assertTrue(
                (project / "images" / "board-01.model-generated.png").is_file()
            )
            self.assertFalse(
                (project / "images" / "board-02.model-generated.png").exists()
            )
            self.assertFalse((project / "board_asset_manifest.json").exists())

    def test_doctor_reports_auto_provider_without_exposing_key(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "WHITEBOARD_IMAGE_MODE": "auto",
                "WHITEBOARD_IMAGE_PROVIDER": "openai",
                "OPENAI_API_KEY": "doctor-secret-key",
            }
        )
        result = subprocess.run(
            [sys.executable, str(DOCTOR), "--json", "--skip-hyperframes-probe"],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("doctor-secret-key", result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["image"], "PASS")
        image_check = next(item for item in report["checks"] if item["id"] == "image.mode")
        self.assertTrue(image_check["details"]["api_key_present"])


if __name__ == "__main__":
    unittest.main()
