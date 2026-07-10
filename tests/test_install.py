from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install.py"
FORBIDDEN_MEDIA = {".aiff", ".jpeg", ".jpg", ".mov", ".mp3", ".mp4", ".png", ".wav"}


class InstallTests(unittest.TestCase):
    def run_installer(self, *args: object, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *map(str, args)],
            cwd=REPO_ROOT,
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

    def assert_complete_install(self, skill_root: Path, target: str) -> None:
        marker = json.loads((skill_root / "installation.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["product"], "whiteboard-video")
        self.assertEqual(marker["target"], target)
        self.assertRegex(marker["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue((skill_root / "SKILL.md").is_file())
        self.assertTrue((skill_root / "agents" / "openai.yaml").is_file())
        self.assertTrue((skill_root / "scripts" / "doctor.py").is_file())
        self.assertTrue((skill_root / "runtime" / "scripts" / "doctor.py").is_file())
        for module in (
            "ip-cognition-script-polisher",
            "ip-hand-drawn-infographic-planner",
            "hand-drawn-infographic-creator",
            "hand-drawn-infographic-video-board",
            "whiteboard-infographic-video-renderer",
            "whiteboard-infographic-pipeline-orchestrator",
        ):
            self.assertTrue(
                (skill_root / "runtime" / module / "INTERNAL_SKILL.md").is_file()
            )
            self.assertFalse((skill_root / "runtime" / module / "SKILL.md").exists())
        self.assertTrue(
            (
                skill_root
                / "runtime"
                / "whiteboard-infographic-pipeline-orchestrator"
                / "scripts"
                / "validate_release_candidate.py"
            ).is_file()
        )

        discovered = list(skill_root.rglob("SKILL.md"))
        self.assertEqual(discovered, [skill_root / "SKILL.md"])

        for path in skill_root.rglob("*"):
            if path.is_file():
                self.assertNotIn(path.suffix.lower(), FORBIDDEN_MEDIA, str(path))
                developer_prefix = "/Users/" + "yanzhengkai"
                self.assertNotIn(
                    developer_prefix, path.read_bytes().decode("utf-8", "ignore")
                )

    def test_codex_install_is_self_contained_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills_dir = root / "Codex Skills 中文"
            first = self.run_installer(
                "--target",
                "codex",
                "--codex-skills-dir",
                skills_dir,
            )
            self.assertIn("PASS installed", first.stdout)
            skill_root = skills_dir / "whiteboard-video"
            self.assert_complete_install(skill_root, "codex")
            marker_mtime = (skill_root / "installation.json").stat().st_mtime_ns

            second = self.run_installer(
                "--target",
                "codex",
                "--codex-skills-dir",
                skills_dir,
            )
            self.assertIn("already current", second.stdout)
            self.assertEqual(marker_mtime, (skill_root / "installation.json").stat().st_mtime_ns)

            report = self.run_doctor(skill_root, root / "outputs")
            self.assertEqual(report["summary"]["install"], "PASS")
            self.assertEqual(report["summary"]["render"], "WARN")
            self.assertEqual(report["summary"]["image"], "WARN")
            self.assertTrue(Path(report["runtime_root"]).is_relative_to(skill_root.resolve()))
            runtime = skill_root / "runtime"
            validation = subprocess.run(
                [
                    sys.executable,
                    str(
                        runtime
                        / "whiteboard-infographic-pipeline-orchestrator"
                        / "scripts"
                        / "validate_orchestrator_inputs.py"
                    ),
                    "--workspace",
                    str(runtime),
                    "--topic-input",
                    str(
                        runtime
                        / "whiteboard-infographic-pipeline-orchestrator"
                        / "examples"
                        / "minimal-topic-input.txt"
                    ),
                    "--project-dir",
                    str(root / "new-project"),
                    "--json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertTrue(json.loads(validation.stdout)["ok"])

    def test_claude_and_both_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_dir = root / "agents" / "skills"
            claude_dir = root / "claude" / "skills"
            self.run_installer(
                "--target",
                "both",
                "--codex-skills-dir",
                codex_dir,
                "--claude-skills-dir",
                claude_dir,
            )
            self.assert_complete_install(codex_dir / "whiteboard-video", "codex")
            self.assert_complete_install(claude_dir / "whiteboard-video", "claude")

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skills_dir = Path(temporary) / "skills"
            result = self.run_installer(
                "--target",
                "codex",
                "--codex-skills-dir",
                skills_dir,
                "--dry-run",
            )
            self.assertIn("No files were written", result.stdout)
            self.assertFalse(skills_dir.exists())

    def test_auto_target_respects_explicit_codex_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills_dir = root / "skills"
            result = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    "auto",
                    "--codex-skills-dir",
                    str(skills_dir),
                ],
                cwd=REPO_ROOT,
                env={"HOME": str(root), "PATH": ""},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_complete_install(skills_dir / "whiteboard-video", "codex")
            self.assertNotIn("[claude]", result.stdout)

    def test_refuses_unmanaged_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary) / "skills" / "whiteboard-video"
            skill_root.mkdir(parents=True)
            sentinel = skill_root / "keep.txt"
            sentinel.write_text("user file", encoding="utf-8")
            result = self.run_installer(
                "--target",
                "codex",
                "--codex-skills-dir",
                skill_root.parent,
                expected=2,
            )
            self.assertIn("Refusing to overwrite", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "user file")

    def test_changed_install_requires_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skills_dir = Path(temporary) / "skills"
            self.run_installer(
                "--target",
                "claude",
                "--claude-skills-dir",
                skills_dir,
            )
            marker_path = skills_dir / "whiteboard-video" / "installation.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["source_digest"] = "older-source"
            marker_path.write_text(json.dumps(marker), encoding="utf-8")

            result = self.run_installer(
                "--target",
                "claude",
                "--claude-skills-dir",
                skills_dir,
                expected=2,
            )
            self.assertIn("--upgrade", result.stderr)
            upgraded = self.run_installer(
                "--target",
                "claude",
                "--claude-skills-dir",
                skills_dir,
                "--upgrade",
            )
            self.assertIn("PASS installed", upgraded.stdout)
            refreshed = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertNotEqual(refreshed["source_digest"], "older-source")

    def test_doctor_reports_missing_render_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills_dir = root / "skills"
            self.run_installer(
                "--target",
                "codex",
                "--codex-skills-dir",
                skills_dir,
            )
            skill_root = skills_dir / "whiteboard-video"
            result = subprocess.run(
                [
                    sys.executable,
                    str(skill_root / "scripts" / "doctor.py"),
                    "--json",
                    "--skip-hyperframes-probe",
                    "--output-dir",
                    str(root / "outputs"),
                ],
                cwd=root,
                env={**os.environ, "PATH": str(root / "empty-path")},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["summary"]["install"], "PASS")
            self.assertEqual(report["summary"]["render"], "FAIL")
            self.assertEqual(report["summary"]["overall"], "WARN")

    def run_doctor(self, skill_root: Path, output_dir: Path) -> dict[str, object]:
        fake_bin = output_dir.parent / "fake-bin"
        fake_bin.mkdir()
        for executable, version in (
            ("node", "v20.19.0"),
            ("ffmpeg", "ffmpeg version test"),
            ("ffprobe", "ffprobe version test"),
            ("edge-tts", "edge-tts 7.0.0"),
            ("npx", "10.0.0"),
        ):
            path = fake_bin / executable
            path.write_text(f"#!/bin/sh\necho '{version}'\n", encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        result = subprocess.run(
            [
                sys.executable,
                str(skill_root / "scripts" / "doctor.py"),
                "--json",
                "--skip-hyperframes-probe",
                "--output-dir",
                str(output_dir),
            ],
            cwd=output_dir.parent,
            env={**os.environ, "PATH": str(fake_bin)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)


if __name__ == "__main__":
    unittest.main()
