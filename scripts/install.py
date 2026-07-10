#!/usr/bin/env python3
"""Install the public whiteboard-video Skill for Codex and/or Claude Code."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Callable


SKILL_NAME = "whiteboard-video"
PRODUCT_ID = "whiteboard-video"
REPOSITORY = "https://github.com/zkbys/whiteboard.git"
SOURCE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SOURCE = SOURCE_ROOT / "skills" / SKILL_NAME
MARKER_NAME = "installation.json"

RUNTIME_ITEMS = (
    "ip-cognition-script-polisher",
    "ip-hand-drawn-infographic-planner",
    "hand-drawn-infographic-creator",
    "hand-drawn-infographic-video-board",
    "whiteboard-infographic-video-renderer",
    "whiteboard-infographic-pipeline-orchestrator",
    "LICENSE",
)

IGNORED_NAMES = {
    ".DS_Store",
    ".git",
    "__pycache__",
    "node_modules",
    "runs",
    "orchestrator-runs",
    ".playwright-cli",
}
IGNORED_SUFFIXES = {
    ".aiff",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".png",
    ".pyc",
    ".wav",
}


class InstallError(RuntimeError):
    """Raised for a safe, user-facing installation refusal."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install the self-contained whiteboard-video Skill without sudo or "
            "symlinks. Codex defaults to ~/.agents/skills; Claude Code defaults "
            "to ~/.claude/skills."
        )
    )
    parser.add_argument(
        "--target",
        choices=("codex", "claude", "both", "auto"),
        default="auto",
        help="Agent target. auto detects installed CLIs or existing config directories.",
    )
    parser.add_argument(
        "--codex-skills-dir",
        type=Path,
        help="Override the Codex skills directory (default: ~/.agents/skills).",
    )
    parser.add_argument(
        "--claude-skills-dir",
        type=Path,
        help="Override the Claude Code skills directory (default: ~/.claude/skills).",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Replace an older installation owned by this project.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned operation without writing files.",
    )
    return parser.parse_args()


def ignored(_directory: str, names: list[str]) -> set[str]:
    ignored_names: set[str] = set()
    for name in names:
        if name in IGNORED_NAMES or Path(name).suffix.lower() in IGNORED_SUFFIXES:
            ignored_names.add(name)
    return ignored_names


def iter_payload_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    roots = [(f"skill/{SKILL_SOURCE.name}", SKILL_SOURCE)]
    for item in RUNTIME_ITEMS:
        roots.append((f"runtime/{item}", SOURCE_ROOT / item))
    roots.append(("runtime/scripts/doctor.py", SOURCE_ROOT / "scripts" / "doctor.py"))
    roots.append(("package/scripts/install.py", SOURCE_ROOT / "scripts" / "install.py"))
    roots.append(("package/package.json", SOURCE_ROOT / "package.json"))

    for prefix, path in roots:
        if path.is_file():
            files.append((prefix, path))
            continue
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            relative_parts = child.relative_to(path).parts
            if any(part in IGNORED_NAMES for part in relative_parts):
                continue
            if child.suffix.lower() in IGNORED_SUFFIXES:
                continue
            files.append((f"{prefix}/{child.relative_to(path).as_posix()}", child))
    return files


def source_digest() -> str:
    digest = hashlib.sha256()
    for relative, path in iter_payload_files():
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def package_version() -> str:
    package = json.loads((SOURCE_ROOT / "package.json").read_text(encoding="utf-8"))
    return str(package.get("version", "0.0.0"))


def validate_source() -> None:
    required = [SKILL_SOURCE / "SKILL.md", SOURCE_ROOT / "scripts" / "doctor.py"]
    required.extend(SOURCE_ROOT / item for item in RUNTIME_ITEMS)
    missing = [str(path.relative_to(SOURCE_ROOT)) for path in required if not path.exists()]
    if missing:
        raise InstallError("Source checkout is incomplete: " + ", ".join(missing))


def default_codex_skills_dir() -> Path:
    return Path.home() / ".agents" / "skills"


def default_claude_skills_dir() -> Path:
    return Path.home() / ".claude" / "skills"


def detect_targets(args: argparse.Namespace) -> list[str]:
    if args.target == "both":
        return ["codex", "claude"]
    if args.target in {"codex", "claude"}:
        return [args.target]

    detected: list[str] = []
    if (
        args.codex_skills_dir
        or shutil.which("codex")
        or (Path.home() / ".agents").exists()
        or os.environ.get("CODEX_HOME")
    ):
        detected.append("codex")
    if (
        args.claude_skills_dir
        or shutil.which("claude")
        or (Path.home() / ".claude").exists()
        or os.environ.get("CLAUDE_CONFIG_DIR")
    ):
        detected.append("claude")
    if not detected:
        raise InstallError(
            "--target auto could not detect Codex or Claude Code. "
            "Run again with --target codex, --target claude, or --target both."
        )
    return detected


def skills_dir_for(target: str, args: argparse.Namespace) -> Path:
    if target == "codex":
        path = args.codex_skills_dir or default_codex_skills_dir()
    else:
        path = args.claude_skills_dir or default_claude_skills_dir()
    return path.expanduser().resolve()


def read_marker(destination: Path) -> dict[str, object] | None:
    marker_path = destination / MARKER_NAME
    if not marker_path.is_file():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"Cannot read installation marker at {marker_path}: {exc}") from exc
    if marker.get("product") != PRODUCT_ID:
        return None
    return marker


def planned_action(destination: Path, digest: str, allow_upgrade: bool) -> str:
    if not destination.exists():
        return "install"
    if not destination.is_dir():
        raise InstallError(f"Refusing to overwrite non-directory path: {destination}")
    marker = read_marker(destination)
    if marker is None:
        raise InstallError(
            f"Refusing to overwrite existing non-{PRODUCT_ID} directory: {destination}"
        )
    if marker.get("source_digest") == digest:
        return "already-current"
    if not allow_upgrade:
        raise InstallError(
            f"An older {PRODUCT_ID} installation exists at {destination}. "
            "Review it, then rerun with --upgrade."
        )
    return "upgrade"


def copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, ignore=ignored)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_installation(stage: Path, target: str, digest: str) -> None:
    shutil.copytree(SKILL_SOURCE, stage, ignore=ignored)
    runtime = stage / "runtime"
    runtime.mkdir()
    for item in RUNTIME_ITEMS:
        copy_path(SOURCE_ROOT / item, runtime / item)
    copy_path(SOURCE_ROOT / "scripts" / "doctor.py", runtime / "scripts" / "doctor.py")
    for module in RUNTIME_ITEMS[:6]:
        public_entry = runtime / module / "SKILL.md"
        internal_entry = runtime / module / "INTERNAL_SKILL.md"
        if public_entry.is_file():
            public_entry.rename(internal_entry)

    marker = {
        "schema_version": 1,
        "product": PRODUCT_ID,
        "skill_name": SKILL_NAME,
        "target": target,
        "repository": REPOSITORY,
        "version": package_version(),
        "source_digest": digest,
        "runtime": "runtime",
        "internal_skill_entry": "INTERNAL_SKILL.md",
    }
    (stage / MARKER_NAME).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def atomic_replace(destination: Path, builder: Callable[[Path], None]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    stage = destination.parent / f".{destination.name}.stage-{token}"
    backup = destination.parent / f".{destination.name}.backup-{token}"
    try:
        builder(stage)
        if destination.exists():
            destination.rename(backup)
        stage.rename(destination)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        if backup.exists() and not destination.exists():
            backup.rename(destination)
        raise


def print_next_steps(target: str, destination: Path) -> None:
    doctor = destination / "scripts" / "doctor.py"
    print(f"[{target}] Doctor: {sys.executable} {doctor} --json")
    if target == "codex":
        print(
            "[codex] Invoke: 请使用 whiteboard-video skill 帮我做一个视频，"
            "主题为“AI 工具越多，普通人反而越低效”，时长 30-60 秒。"
        )
        print("[codex] Codex usually detects Skills automatically; restart if it does not appear.")
    else:
        print(
            "[claude] Invoke: /whiteboard-video 主题为“AI 工具越多，普通人反而越低效”，"
            "时长 30-60 秒。"
        )
        print(
            "[claude] Restart only if ~/.claude/skills did not exist when the current session began."
        )


def main() -> int:
    args = parse_args()
    try:
        validate_source()
        digest = source_digest()
        targets = detect_targets(args)
        operations: list[tuple[str, Path, str]] = []
        for target in targets:
            destination = skills_dir_for(target, args) / SKILL_NAME
            action = planned_action(destination, digest, args.upgrade)
            operations.append((target, destination, action))

        for target, destination, action in operations:
            verb = "DRY-RUN" if args.dry_run else "PLAN"
            print(f"[{target}] {verb} {action}: {destination}")

        if args.dry_run:
            print("No files were written.")
            return 0

        for target, destination, action in operations:
            if action == "already-current":
                print(f"[{target}] PASS already current: {destination}")
                print_next_steps(target, destination)
                continue
            atomic_replace(
                destination,
                lambda stage, selected=target: build_installation(stage, selected, digest),
            )
            print(f"[{target}] PASS installed: {destination}")
            print_next_steps(target, destination)
        return 0
    except InstallError as exc:
        print(f"INSTALL FAIL: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"INSTALL FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
