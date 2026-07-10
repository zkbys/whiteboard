#!/usr/bin/env python3
"""Generate or plan model PNG assets for a whiteboard-video project."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from write_board_asset_manifest import load_expected_boards, read_png_size


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
PROVIDERS = ("auto", "interactive", "openai", "command")


class GenerationError(RuntimeError):
    """Raised for a safe, user-facing image generation failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate images/<boardId>.model-generated.png through a configured "
            "provider, or emit an exact interactive handoff plan."
        )
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--provider", choices=PROVIDERS, default="auto")
    parser.add_argument(
        "--command",
        help=(
            "Executable for the command provider. It receives --prompt-file, "
            "--output-file, and --board-id. Defaults to WHITEBOARD_IMAGE_COMMAND."
        ),
    )
    parser.add_argument(
        "--api-key-env",
        default=os.environ.get("WHITEBOARD_OPENAI_API_KEY_ENV", "OPENAI_API_KEY"),
        help="Environment variable containing the OpenAI API key.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible API base URL ending in /v1.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("WHITEBOARD_OPENAI_IMAGE_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--size",
        choices=("1024x1024", "1024x1536", "1536x1024", "auto"),
        default="1536x1024",
    )
    parser.add_argument(
        "--quality",
        choices=("low", "medium", "high", "auto"),
        default="medium",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--min-width", type=int, default=512)
    parser.add_argument("--min-height", type=int, default=512)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        help="Defaults to <project-dir>/image_generation_report.json.",
    )
    return parser.parse_args()


def relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolve_provider(args: argparse.Namespace) -> str:
    if args.provider != "auto":
        return args.provider
    configured = os.environ.get("WHITEBOARD_IMAGE_PROVIDER", "").strip().lower()
    if configured:
        if configured not in PROVIDERS or configured == "auto":
            raise GenerationError(
                "WHITEBOARD_IMAGE_PROVIDER must be interactive, openai, or command."
            )
        return configured
    if args.command or os.environ.get("WHITEBOARD_IMAGE_COMMAND"):
        return "command"
    return "interactive"


def resolve_command(args: argparse.Namespace) -> str:
    command = args.command or os.environ.get("WHITEBOARD_IMAGE_COMMAND", "")
    if not command:
        raise GenerationError(
            "The command provider requires --command or WHITEBOARD_IMAGE_COMMAND."
        )
    expanded = str(Path(command).expanduser())
    resolved = shutil.which(expanded)
    if resolved:
        return resolved
    path = Path(expanded)
    if path.is_file() and os.access(path, os.X_OK):
        return str(path.resolve())
    raise GenerationError(f"Image provider command is not executable: {command}")


def load_board_jobs(project_dir: Path) -> list[dict[str, Any]]:
    plan_path = project_dir / "infographic" / "infographic_plan.json"
    if not plan_path.is_file():
        raise GenerationError(f"Infographic plan not found: {plan_path}")
    boards = load_expected_boards(project_dir, plan_path)
    if not boards:
        raise GenerationError(f"No boards found in {plan_path}")

    jobs: list[dict[str, Any]] = []
    for board in boards:
        board_id = board["boardId"]
        prompt_path = project_dir / "imagegen_prompts" / f"{board_id}.imagegen_prompt.txt"
        if not prompt_path.is_file():
            raise GenerationError(f"Image prompt not found: {prompt_path}")
        if not prompt_path.read_text(encoding="utf-8").strip():
            raise GenerationError(f"Image prompt is empty: {prompt_path}")
        jobs.append(
            {
                "boardId": board_id,
                "title": board.get("title", ""),
                "promptPath": prompt_path,
                "outputPath": project_dir / "images" / f"{board_id}.model-generated.png",
            }
        )
    return jobs


def validate_png(path: Path, min_width: int, min_height: int) -> tuple[int, int]:
    width, height = read_png_size(path)
    if width < min_width or height < min_height:
        raise GenerationError(
            f"{path} is {width}x{height}; expected at least {min_width}x{min_height}."
        )
    return width, height


def openai_generate(prompt: str, args: argparse.Namespace) -> tuple[bytes, dict[str, Any]]:
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise GenerationError(
            f"OpenAI provider requires a non-empty {args.api_key_env} environment variable."
        )
    payload = {
        "model": args.model,
        "prompt": prompt,
        "n": 1,
        "size": args.size,
        "quality": args.quality,
        "output_format": "png",
    }
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "whiteboard-video/0.2",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read(1200).decode("utf-8", "replace")
        body = body.replace(api_key, "[REDACTED]")
        raise GenerationError(f"OpenAI image request failed with HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GenerationError(f"OpenAI image request failed: {exc}") from exc

    if not isinstance(response_data, dict):
        raise GenerationError("OpenAI image response was not a JSON object.")
    images = response_data.get("data")
    first_image = (
        images[0]
        if isinstance(images, list) and images and isinstance(images[0], dict)
        else {}
    )
    encoded = first_image.get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise GenerationError("OpenAI image response did not contain data[0].b64_json.")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise GenerationError("OpenAI image response contained invalid base64 data.") from exc
    return image_bytes, {"usage": response_data.get("usage")}


def command_generate(
    command: str, job: dict[str, Any], temporary: Path, timeout: float
) -> dict[str, Any]:
    result = subprocess.run(
        [
            command,
            "--prompt-file",
            str(job["promptPath"]),
            "--output-file",
            str(temporary),
            "--board-id",
            str(job["boardId"]),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        output = result.stdout.strip()[-1200:]
        raise GenerationError(
            f"Command provider failed for {job['boardId']} with exit "
            f"{result.returncode}: {output}"
        )
    if not temporary.is_file():
        raise GenerationError(
            f"Command provider did not write the requested PNG: {temporary}"
        )
    return {"commandExitCode": result.returncode}


def run_manifest(
    project_dir: Path,
    provider: str,
    args: argparse.Namespace,
    preview_checked: bool,
) -> Path:
    script = Path(__file__).resolve().with_name("write_board_asset_manifest.py")
    mode = (
        "built-in image_gen preview with manual download"
        if preview_checked
        else f"auto:{provider}" + (f":{args.model}" if provider == "openai" else "")
    )
    preview_check = (
        "confirmed model-generated board for this run; not D SVG and not old smoke preview"
        if preview_checked
        else f"generated and saved directly by {mode}; validated PNG before D/E"
    )
    command = [
        sys.executable,
        str(script),
        "--project-dir",
        str(project_dir),
        "--overwrite",
        "--mode",
        mode,
        "--preview-check",
        preview_check,
        "--min-width",
        str(args.min_width),
        "--min-height",
        str(args.min_height),
    ]
    if not preview_checked:
        command.append("--no-preview-checked")
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GenerationError(f"Manifest generation failed: {result.stdout.strip()[-1600:]}")
    return project_dir / "board_asset_manifest.json"


def base_report(
    project_dir: Path,
    report_path: Path,
    requested: str,
    resolved: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "running",
        "providerRequested": requested,
        "providerResolved": resolved,
        "automatic": resolved != "interactive",
        "projectDir": str(project_dir),
        "reportPath": relative(report_path, project_dir),
        "model": args.model if resolved == "openai" else None,
        "size": args.size if resolved == "openai" else None,
        "quality": args.quality if resolved == "openai" else None,
        "apiKeyEnv": args.api_key_env if resolved == "openai" else None,
        "boards": [],
        "manifestPath": None,
    }


def execute(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        raise GenerationError(f"Project directory not found: {project_dir}")
    report_path = (args.report or project_dir / "image_generation_report.json").expanduser().resolve()
    provider = resolve_provider(args)
    jobs = load_board_jobs(project_dir)
    report = base_report(project_dir, report_path, args.provider, provider, args)

    if args.dry_run:
        report["status"] = "dry_run"
        report["boards"] = [
            {
                "boardId": job["boardId"],
                "promptPath": relative(job["promptPath"], project_dir),
                "outputPath": relative(job["outputPath"], project_dir),
                "status": "planned",
            }
            for job in jobs
        ]
        return 0, report

    (project_dir / "images").mkdir(parents=True, exist_ok=True)
    command = resolve_command(args) if provider == "command" else None
    missing_interactive = False
    for job in jobs:
        output_path: Path = job["outputPath"]
        board_report: dict[str, Any] = {
            "boardId": job["boardId"],
            "promptPath": relative(job["promptPath"], project_dir),
            "outputPath": relative(output_path, project_dir),
        }
        temporary: Path | None = None
        try:
            if output_path.is_file() and not args.overwrite:
                width, height = validate_png(output_path, args.min_width, args.min_height)
                board_report.update({"status": "reused", "width": width, "height": height})
                report["boards"].append(board_report)
                continue
            if provider == "interactive":
                board_report["status"] = "manual_save_required"
                report["boards"].append(board_report)
                missing_interactive = True
                continue

            temporary = output_path.with_name(f".{output_path.stem}.{os.getpid()}.tmp.png")
            if temporary.exists():
                temporary.unlink()
            if provider == "openai":
                prompt = job["promptPath"].read_text(encoding="utf-8").strip()
                image_bytes, metadata = openai_generate(prompt, args)
                temporary.write_bytes(image_bytes)
            else:
                metadata = command_generate(str(command), job, temporary, args.timeout)
            width, height = validate_png(temporary, args.min_width, args.min_height)
            temporary.replace(output_path)
        except (GenerationError, OSError, subprocess.TimeoutExpired) as exc:
            board_report.update({"status": "failed", "error": str(exc)})
            report["boards"].append(board_report)
            report.update({"status": "failed", "error": str(exc)})
            return 2, report
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        board_report.update(
            {"status": "generated", "width": width, "height": height, **metadata}
        )
        report["boards"].append(board_report)

    if missing_interactive:
        report["status"] = "handoff_required"
        return 3, report

    try:
        manifest = run_manifest(
            project_dir,
            provider,
            args,
            preview_checked=provider == "interactive",
        )
    except (GenerationError, OSError, subprocess.TimeoutExpired) as exc:
        report.update({"status": "failed", "error": str(exc)})
        return 2, report
    report["manifestPath"] = relative(manifest, project_dir)
    report["status"] = "complete"
    return 0, report


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    report_path = (args.report or project_dir / "image_generation_report.json").expanduser().resolve()
    try:
        code, report = execute(args)
    except (GenerationError, OSError, subprocess.TimeoutExpired) as exc:
        try:
            provider = resolve_provider(args)
        except GenerationError:
            provider = "unresolved"
        report = base_report(project_dir, report_path, args.provider, provider, args)
        report.update({"status": "failed", "error": str(exc)})
        if not args.dry_run and project_dir.is_dir():
            write_json_atomic(report_path, report)
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        write_json_atomic(report_path, report)
        print(f"[{report['status'].upper()}] image provider: {report['providerResolved']}")
        print(f"report: {report_path}")
        for board in report["boards"]:
            print(f"- {board['boardId']}: {board['status']} -> {board['outputPath']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
