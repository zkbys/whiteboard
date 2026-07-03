#!/usr/bin/env python3
"""Validate an ip-hand-drawn-infographic-planner output package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
REQUIRED_PROMPT_PHRASE = "内容简洁一点，不要逐字写满口播"
ALLOWED_DIAGRAM_TYPES = {
    "process_flow",
    "comparison",
    "two_panel_comparison",
    "timeline",
    "knowledge_map",
    "checklist_flow",
    "flywheel",
}
PROMPT_REQUIRED_TERMS = [
    "continuous line art",
    "engineer's notebook sketch",
    "whiteboard explanation aesthetic",
    "#faf8f3",
    "#1a2332",
    "#2d5a7b",
]
NEGATIVE_PROMPT_TERMS = ["photorealistic", "3d render", "stock photo"]
CONTROL_LAYER_KEYS = {
    "bbox",
    "camera",
    "cursor",
    "annotations",
    "boxBounds",
    "circleCenter",
    "underlineStart",
    "underlineEnd",
    "strikeStart",
    "strikeEnd",
}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc


def resolve_paths(root: Path) -> tuple[Path, Path, Path]:
    root = root.resolve()
    direct_plan = root / "infographic_plan.json"
    nested_plan = root / "infographic" / "infographic_plan.json"

    if direct_plan.exists():
        infographic_dir = root
        project_dir = root.parent
        plan_path = direct_plan
    elif nested_plan.exists():
        project_dir = root
        infographic_dir = root / "infographic"
        plan_path = nested_plan
    else:
        raise ValidationError(
            f"Could not find infographic_plan.json under {root} or {root / 'infographic'}"
        )

    return project_dir, infographic_dir, plan_path


def resolve_artifact_path(project_dir: Path, infographic_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path

    project_relative = project_dir / path
    if project_relative.exists():
        return project_relative

    return infographic_dir / path


def require_id(value: Any, context: str) -> None:
    if not isinstance(value, str) or not ID_RE.match(value):
        raise ValidationError(f"{context} must be a stable id matching {ID_RE.pattern}: {value!r}")


def require_fields(obj: dict[str, Any], fields: list[str], context: str) -> None:
    for field in fields:
        if field not in obj:
            raise ValidationError(f"{context} missing required field: {field}")


def collect_control_keys(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in CONTROL_LAYER_KEYS:
                findings.append(child_path)
            findings.extend(collect_control_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(collect_control_keys(child, f"{path}[{index}]"))
    return findings


def validate_key_objects(
    objects: Any,
    max_count: int,
    context: str,
    seen_global_ids: set[str],
) -> set[str]:
    if not isinstance(objects, list) or not objects:
        raise ValidationError(f"{context}.keyObjects must be a non-empty list")
    if len(objects) > max_count:
        raise ValidationError(
            f"{context}.keyObjects has {len(objects)} objects, maxKeyObjects is {max_count}"
        )

    local_ids: set[str] = set()
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            raise ValidationError(f"{context}.keyObjects[{index}] must be an object")
        require_fields(item, ["id", "label", "role"], f"{context}.keyObjects[{index}]")
        object_id = item["id"]
        require_id(object_id, f"{context}.keyObjects[{index}].id")
        if object_id in local_ids:
            raise ValidationError(f"Duplicate key object id in {context}: {object_id}")
        if object_id in seen_global_ids:
            raise ValidationError(f"Duplicate key object id across boards: {object_id}")
        if not isinstance(item["label"], str) or not item["label"].strip():
            raise ValidationError(f"{context}.keyObjects[{index}].label must be non-empty")
        local_ids.add(object_id)

    seen_global_ids.update(local_ids)
    return local_ids


def validate_prompt(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text_lower = text.lower()

    if REQUIRED_PROMPT_PHRASE not in text:
        raise ValidationError(f"{path} missing required phrase: {REQUIRED_PROMPT_PHRASE}")

    for term in PROMPT_REQUIRED_TERMS:
        if term.lower() not in text_lower:
            raise ValidationError(f"{path} missing required prompt term/color: {term}")

    for term in NEGATIVE_PROMPT_TERMS:
        if term not in text_lower:
            raise ValidationError(f"{path} negative prompt missing: {term}")


def validate_board_spec(
    spec_path: Path,
    board: dict[str, Any],
    plan_object_ids: set[str],
    prompt_path: Path,
) -> None:
    spec = load_json(spec_path)
    if not isinstance(spec, dict):
        raise ValidationError(f"{spec_path} must contain a JSON object")

    require_fields(
        spec,
        ["id", "title", "diagramType", "canvas", "style", "layout", "keyObjects", "imagePromptPath"],
        str(spec_path),
    )
    if spec["id"] != board["id"]:
        raise ValidationError(f"{spec_path} id does not match plan board id {board['id']}")
    if spec["diagramType"] != board["diagramType"]:
        raise ValidationError(f"{spec_path} diagramType does not match plan")

    canvas = spec["canvas"]
    if not isinstance(canvas, dict):
        raise ValidationError(f"{spec_path}.canvas must be an object")
    for field in ["width", "height"]:
        if not isinstance(canvas.get(field), int) or canvas[field] <= 0:
            raise ValidationError(f"{spec_path}.canvas.{field} must be a positive integer")

    control_keys = collect_control_keys(spec)
    if control_keys:
        joined = ", ".join(control_keys[:8])
        raise ValidationError(f"{spec_path} contains control-layer keys not allowed here: {joined}")

    spec_object_ids = validate_key_objects(
        spec["keyObjects"],
        int(board["maxKeyObjects"]),
        str(spec_path),
        set(),
    )
    if spec_object_ids != plan_object_ids:
        raise ValidationError(
            f"{spec_path} key object ids do not match plan: {sorted(spec_object_ids)} != {sorted(plan_object_ids)}"
        )

    spec_prompt = Path(spec["imagePromptPath"])
    if spec_prompt.name != prompt_path.name:
        raise ValidationError(f"{spec_path}.imagePromptPath does not point to {prompt_path.name}")


def validate(root: Path) -> list[str]:
    project_dir, infographic_dir, plan_path = resolve_paths(root)
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        raise ValidationError(f"{plan_path} must contain a JSON object")

    require_fields(plan, ["version", "source", "boardDecision", "styleBridge", "boards"], str(plan_path))
    boards = plan["boards"]
    if not isinstance(boards, list) or not boards:
        raise ValidationError("infographic_plan.json boards must be a non-empty list")
    if len(boards) > 3:
        raise ValidationError("Use at most 3 boards for this planner Skill")

    board_decision = plan["boardDecision"]
    if not isinstance(board_decision, dict):
        raise ValidationError("boardDecision must be an object")
    if board_decision.get("boardCount") != len(boards):
        raise ValidationError("boardDecision.boardCount must match boards length")
    if not board_decision.get("reason"):
        raise ValidationError("boardDecision.reason must explain why this board count was chosen")

    seen_board_ids: set[str] = set()
    seen_global_object_ids: set[str] = set()
    validated: list[str] = []

    for index, board in enumerate(boards):
        context = f"boards[{index}]"
        if not isinstance(board, dict):
            raise ValidationError(f"{context} must be an object")
        require_fields(
            board,
            [
                "id",
                "title",
                "purpose",
                "contentDensity",
                "maxKeyObjects",
                "sourceSegments",
                "diagramType",
                "keyObjects",
                "imagePromptPath",
                "boardSpecPath",
            ],
            context,
        )

        require_id(board["id"], f"{context}.id")
        if board["id"] in seen_board_ids:
            raise ValidationError(f"Duplicate board id: {board['id']}")
        seen_board_ids.add(board["id"])

        if board["contentDensity"] != "simple":
            raise ValidationError(f"{context}.contentDensity must be simple")
        if not isinstance(board["maxKeyObjects"], int) or not (3 <= board["maxKeyObjects"] <= 5):
            raise ValidationError(f"{context}.maxKeyObjects must be an integer from 3 to 5")
        if board["diagramType"] not in ALLOWED_DIAGRAM_TYPES:
            raise ValidationError(f"{context}.diagramType is not allowed: {board['diagramType']}")
        if not isinstance(board["sourceSegments"], list) or not board["sourceSegments"]:
            raise ValidationError(f"{context}.sourceSegments must be a non-empty list")

        plan_object_ids = validate_key_objects(
            board["keyObjects"],
            board["maxKeyObjects"],
            context,
            seen_global_object_ids,
        )

        spec_path = resolve_artifact_path(project_dir, infographic_dir, board["boardSpecPath"])
        prompt_path = resolve_artifact_path(project_dir, infographic_dir, board["imagePromptPath"])
        validate_prompt(prompt_path)
        validate_board_spec(spec_path, board, plan_object_ids, prompt_path)
        validated.append(board["id"])

    return validated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate infographic_plan.json, board specs, and image prompts."
    )
    parser.add_argument("path", help="Project root or infographic directory")
    args = parser.parse_args()

    try:
        boards = validate(Path(args.path))
    except ValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] validated infographic plan for boards: {', '.join(boards)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
