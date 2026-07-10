#!/usr/bin/env python3
"""Diagnose whiteboard-video installation and rendering readiness."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_NAME = "whiteboard-video"
HYPERFRAMES_PACKAGE = "hyperframes@0.6.99"
SOURCE_ROOT = Path(__file__).resolve().parents[1]
MODULE_FILES = (
    "ip-cognition-script-polisher/SKILL.md",
    "ip-hand-drawn-infographic-planner/SKILL.md",
    "hand-drawn-infographic-creator/SKILL.md",
    "hand-drawn-infographic-video-board/SKILL.md",
    "whiteboard-infographic-video-renderer/SKILL.md",
    "whiteboard-infographic-pipeline-orchestrator/SKILL.md",
    "whiteboard-infographic-pipeline-orchestrator/references/runbook.md",
    "whiteboard-infographic-pipeline-orchestrator/references/contracts.md",
    "whiteboard-infographic-pipeline-orchestrator/scripts/generate_board_images.py",
)
SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/doctor.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report installation, render dependency, output, and image-mode status "
            "using PASS/WARN/FAIL."
        )
    )
    parser.add_argument("--runtime-root", type=Path, help="Override the internal runtime root.")
    parser.add_argument("--skill-root", type=Path, help="Override the public Skill root.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "whiteboard-runs",
        help="Directory where generated projects will be written.",
    )
    parser.add_argument(
        "--image-mode",
        choices=("interactive", "auto"),
        default=os.environ.get("WHITEBOARD_IMAGE_MODE", "interactive"),
        help="Current image mode. auto validates the configured OpenAI or command provider.",
    )
    parser.add_argument(
        "--skip-hyperframes-probe",
        action="store_true",
        help="Check npx only and report the HyperFrames probe as WARN.",
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=30.0,
        help="Seconds allowed for external version probes.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def load_installation(skill_root: Path) -> dict[str, Any] | None:
    marker = skill_root / "installation.json"
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("product") == SKILL_NAME else None


def resolve_roots(args: argparse.Namespace) -> tuple[Path, Path, bool]:
    skill_root = (args.skill_root or SOURCE_ROOT / "skills" / SKILL_NAME).expanduser().resolve()
    installation = load_installation(skill_root)
    if args.runtime_root:
        runtime_root = args.runtime_root.expanduser().resolve()
    elif installation:
        runtime_value = str(installation.get("runtime", "runtime"))
        runtime_root = (skill_root / runtime_value).resolve()
    else:
        runtime_root = SOURCE_ROOT
    return runtime_root, skill_root, installation is not None


def add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    category: str,
    status: str,
    message: str,
    **details: Any,
) -> None:
    item: dict[str, Any] = {
        "id": check_id,
        "category": category,
        "status": status,
        "message": message,
    }
    if details:
        item["details"] = details
    checks.append(item)


def run_probe(command: list[str], timeout: float) -> tuple[int | None, str]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        clean_version = next(
            (line for line in output if re.fullmatch(r"\d+(?:\.\d+){1,3}", line)),
            None,
        )
        return result.returncode, clean_version or (output[0] if output else "no version output")
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout:g}s"
    except OSError as exc:
        return None, str(exc)


def executable_check(
    checks: list[dict[str, Any]],
    name: str,
    command: list[str],
    timeout: float,
) -> str | None:
    executable = shutil.which(name)
    if not executable:
        add_check(
            checks,
            f"render.{name}",
            "render",
            "FAIL",
            f"{name} was not found on PATH.",
        )
        return None
    code, output = run_probe([executable, *command], timeout)
    if code == 0:
        add_check(
            checks,
            f"render.{name}",
            "render",
            "PASS",
            f"{name} is available: {output}",
            path=executable,
        )
    else:
        add_check(
            checks,
            f"render.{name}",
            "render",
            "FAIL",
            f"{name} probe failed: {output}",
            path=executable,
            exit_code=code,
        )
    return executable


def check_python(checks: list[dict[str, Any]]) -> None:
    version = sys.version_info[:3]
    status = "PASS" if version >= (3, 10, 0) else "FAIL"
    add_check(
        checks,
        "render.python",
        "render",
        status,
        f"Python {'.'.join(map(str, version))}; requires 3.10+.",
        path=sys.executable,
    )


def check_node(checks: list[dict[str, Any]], timeout: float) -> None:
    executable = shutil.which("node")
    if not executable:
        add_check(checks, "render.node", "render", "FAIL", "node was not found on PATH.")
        return
    code, output = run_probe([executable, "--version"], timeout)
    match = re.search(r"(\d+)(?:\.\d+){0,2}", output)
    major = int(match.group(1)) if match else None
    if code == 0 and major is not None and major >= 20:
        status = "PASS"
    else:
        status = "FAIL"
    add_check(
        checks,
        "render.node",
        "render",
        status,
        f"Node.js probe: {output}; requires 20+.",
        path=executable,
        exit_code=code,
    )


def check_files(
    checks: list[dict[str, Any]], runtime_root: Path, skill_root: Path, installed: bool
) -> None:
    expected_runtime_files = [
        path.replace("/SKILL.md", "/INTERNAL_SKILL.md") if installed else path
        for path in MODULE_FILES
    ]
    missing_runtime = [
        path for path in expected_runtime_files if not (runtime_root / path).is_file()
    ]
    add_check(
        checks,
        "install.runtime",
        "install",
        "FAIL" if missing_runtime else "PASS",
        (
            "Internal B/C/Creator/D/E/orchestrator runtime is incomplete."
            if missing_runtime
            else "Internal pipeline runtime is complete."
        ),
        root=str(runtime_root),
        missing=missing_runtime,
    )

    missing_skill = [path for path in SKILL_FILES if not (skill_root / path).is_file()]
    marker_missing = installed and not (skill_root / "installation.json").is_file()
    if marker_missing:
        missing_skill.append("installation.json")
    add_check(
        checks,
        "install.skill",
        "install",
        "FAIL" if missing_skill else "PASS",
        (
            "Public whiteboard-video Skill is incomplete."
            if missing_skill
            else "Public whiteboard-video Skill core is complete."
        ),
        root=str(skill_root),
        mode="installed" if installed else "source-checkout",
        missing=missing_skill,
    )


def nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def check_output(checks: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists() and not output_dir.is_dir():
        add_check(
            checks,
            "output.directory",
            "output",
            "FAIL",
            "Output path exists but is not a directory.",
            path=str(output_dir),
        )
        return
    probe = output_dir if output_dir.exists() else nearest_existing_parent(output_dir)
    writable = probe.is_dir() and os.access(probe, os.W_OK)
    add_check(
        checks,
        "output.directory",
        "output",
        "PASS" if writable else "FAIL",
        (
            "Output directory is writable or can be created."
            if writable
            else "Output directory is not writable."
        ),
        path=str(output_dir),
        tested_parent=str(probe),
    )


def check_image_mode(checks: list[dict[str, Any]], mode: str) -> None:
    if mode == "interactive":
        add_check(
            checks,
            "image.mode",
            "image",
            "WARN",
            (
                "Interactive mode is installable and renderable, but model PNG previews "
                "must be saved manually before D/E."
            ),
            mode=mode,
            automatic_png_provider=False,
        )
        return

    provider = os.environ.get("WHITEBOARD_IMAGE_PROVIDER", "").strip().lower()
    if provider == "openai":
        api_key_env = os.environ.get("WHITEBOARD_OPENAI_API_KEY_ENV", "OPENAI_API_KEY")
        configured = bool(os.environ.get(api_key_env))
        add_check(
            checks,
            "image.mode",
            "image",
            "PASS" if configured else "FAIL",
            (
                "Automatic OpenAI image generation is configured."
                if configured
                else f"OpenAI image provider requires {api_key_env}."
            ),
            mode=mode,
            provider=provider,
            model=os.environ.get("WHITEBOARD_OPENAI_IMAGE_MODEL", "gpt-image-2"),
            api_key_env=api_key_env,
            api_key_present=configured,
            automatic_png_provider=configured,
        )
        return

    if provider == "command":
        command = os.environ.get("WHITEBOARD_IMAGE_COMMAND", "")
        expanded = str(Path(command).expanduser()) if command else ""
        executable = shutil.which(expanded) if expanded else None
        if not executable and expanded:
            path = Path(expanded)
            if path.is_file() and os.access(path, os.X_OK):
                executable = str(path.resolve())
        add_check(
            checks,
            "image.mode",
            "image",
            "PASS" if executable else "FAIL",
            (
                "Automatic command image provider is configured."
                if executable
                else "Command provider requires executable WHITEBOARD_IMAGE_COMMAND."
            ),
            mode=mode,
            provider=provider,
            command=executable,
            automatic_png_provider=bool(executable),
        )
        return

    add_check(
        checks,
        "image.mode",
        "image",
        "FAIL",
        "Auto mode requires WHITEBOARD_IMAGE_PROVIDER=openai or command.",
        mode=mode,
        provider=provider or None,
        automatic_png_provider=False,
    )


def category_status(checks: list[dict[str, Any]], category: str) -> str:
    statuses = [item["status"] for item in checks if item["category"] == category]
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root, skill_root, installed = resolve_roots(args)
    checks: list[dict[str, Any]] = []
    check_files(checks, runtime_root, skill_root, installed)
    check_python(checks)
    check_node(checks, args.probe_timeout)
    executable_check(checks, "ffmpeg", ["-version"], args.probe_timeout)
    executable_check(checks, "ffprobe", ["-version"], args.probe_timeout)
    executable_check(checks, "edge-tts", ["--version"], args.probe_timeout)
    npx = executable_check(checks, "npx", ["--version"], args.probe_timeout)
    if not npx:
        add_check(
            checks,
            "render.hyperframes",
            "render",
            "FAIL",
            "HyperFrames cannot run because npx is unavailable.",
        )
    elif args.skip_hyperframes_probe:
        add_check(
            checks,
            "render.hyperframes",
            "render",
            "WARN",
            "HyperFrames network/cache probe was skipped; npx itself is available.",
            package=HYPERFRAMES_PACKAGE,
        )
    else:
        code, output = run_probe(
            [npx, "--yes", HYPERFRAMES_PACKAGE, "--version"], args.probe_timeout
        )
        add_check(
            checks,
            "render.hyperframes",
            "render",
            "PASS" if code == 0 else "FAIL",
            (
                f"HyperFrames is available: {output}"
                if code == 0
                else f"HyperFrames probe failed: {output}"
            ),
            package=HYPERFRAMES_PACKAGE,
            exit_code=code,
        )
    check_output(checks, args.output_dir)
    check_image_mode(checks, args.image_mode)

    summary = {
        category: category_status(checks, category)
        for category in ("install", "render", "output", "image")
    }
    if summary["install"] == "FAIL" or summary["output"] == "FAIL":
        overall = "FAIL"
    elif summary["render"] != "PASS" or summary["image"] != "PASS":
        overall = "WARN"
    else:
        overall = "PASS"
    summary["overall"] = overall
    return {
        "schema_version": 1,
        "skill": SKILL_NAME,
        "runtime_root": str(runtime_root),
        "skill_root": str(skill_root),
        "output_dir": str(args.output_dir.expanduser().resolve()),
        "summary": summary,
        "checks": checks,
    }


def print_human(report: dict[str, Any]) -> None:
    for item in report["checks"]:
        print(f"[{item['status']}] {item['id']}: {item['message']}")
    summary = report["summary"]
    print(
        "SUMMARY "
        + " ".join(
            f"{name}={summary[name]}"
            for name in ("install", "render", "output", "image", "overall")
        )
    )


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 1 if report["summary"]["overall"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
