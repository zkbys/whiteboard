#!/usr/bin/env python3
"""Validate inputs for a whiteboard infographic pipeline run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


REQUIRED_SKILLS: dict[str, list[str]] = {
    "ip-cognition-script-polisher": [
        "SKILL.md",
        "scripts/validate_script_package.py",
    ],
    "ip-hand-drawn-infographic-planner": [
        "SKILL.md",
        "scripts/validate_infographic_plan.py",
    ],
    "hand-drawn-infographic-creator": [
        "SKILL.md",
    ],
    "hand-drawn-infographic-video-board": [
        "SKILL.md",
        "scripts/generate_board_package.py",
        "scripts/extract_annotation_keyframes.py",
    ],
    "whiteboard-infographic-video-renderer": [
        "SKILL.md",
        "scripts/render_whiteboard_project.mjs",
        "scripts/render_multi_board_project.mjs",
    ],
}


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def add_issue(issues: list[dict[str, str]], code: str, message: str) -> None:
    issues.append({"code": code, "message": message})


def validate(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.expanduser().resolve()
    topic_input = args.topic_input.expanduser().resolve()
    project_dir = args.project_dir.expanduser().resolve()

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not workspace.exists() or not workspace.is_dir():
        add_issue(errors, "workspace_missing", f"Workspace directory not found: {workspace}")
    else:
        for skill_name, required_files in REQUIRED_SKILLS.items():
            skill_dir = workspace / skill_name
            if not skill_dir.exists() or not skill_dir.is_dir():
                add_issue(errors, "skill_missing", f"Required Skill directory missing: {skill_dir}")
                continue
            for rel_path in required_files:
                if rel_path == "SKILL.md" and any(
                    (skill_dir / candidate).is_file()
                    for candidate in ("SKILL.md", "INTERNAL_SKILL.md")
                ):
                    continue
                file_path = skill_dir / rel_path
                if not file_path.exists() or not file_path.is_file():
                    add_issue(errors, "skill_file_missing", f"Required file missing: {file_path}")

    if not topic_input.exists() or not topic_input.is_file():
        add_issue(errors, "topic_input_missing", f"Topic input file not found: {topic_input}")
    else:
        text = read_text(topic_input).strip()
        if len(text) < args.min_chars:
            add_issue(
                errors,
                "topic_input_too_short",
                f"Topic input has {len(text)} chars; expected at least {args.min_chars}.",
            )

    if project_dir.exists():
        if not project_dir.is_dir():
            add_issue(errors, "project_dir_not_directory", f"Project path exists but is not a directory: {project_dir}")
        elif any(project_dir.iterdir()) and args.require_empty_project_dir:
            add_issue(errors, "project_dir_not_empty", f"Project directory is not empty: {project_dir}")
        elif any(project_dir.iterdir()):
            add_issue(warnings, "project_dir_not_empty", f"Project directory already has files: {project_dir}")
    else:
        parent = project_dir.parent
        if not parent.exists() or not parent.is_dir():
            add_issue(errors, "project_parent_missing", f"Project parent directory missing: {parent}")
        elif not os.access(parent, os.W_OK):
            add_issue(errors, "project_parent_not_writable", f"Project parent directory is not writable: {parent}")

    return {
        "ok": not errors,
        "workspace": str(workspace),
        "topicInput": str(topic_input),
        "projectDir": str(project_dir),
        "requiredSkills": sorted(REQUIRED_SKILLS),
        "errors": errors,
        "warnings": warnings,
    }


def print_text_report(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"[{status}] orchestrator input validation")
    print(f"workspace: {report['workspace']}")
    print(f"topicInput: {report['topicInput']}")
    print(f"projectDir: {report['projectDir']}")

    if report["warnings"]:
        print("\nwarnings:")
        for warning in report["warnings"]:
            print(f"- {warning['code']}: {warning['message']}")

    if report["errors"]:
        print("\nerrors:")
        for error in report["errors"]:
            print(f"- {error['code']}: {error['message']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a whiteboard infographic orchestrator run setup.")
    parser.add_argument("--workspace", type=Path, default=default_workspace(), help="Workspace root containing all pipeline Skill folders.")
    parser.add_argument("--topic-input", type=Path, required=True, help="Topic/source script text file.")
    parser.add_argument("--project-dir", type=Path, required=True, help="Project output directory for this run.")
    parser.add_argument("--min-chars", type=int, default=20, help="Minimum non-whitespace characters required in the topic input.")
    parser.add_argument("--require-empty-project-dir", action="store_true", help="Fail if the project directory already exists and has files.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
