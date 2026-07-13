#!/usr/bin/env python3
"""Cross-stage validator: align B voiceover targetElement IDs with C board_spec keyObjects."""

from __future__ import annotations

import datetime
import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_key_object_ids(board_specs: list[Path]) -> dict[str, set[str]]:
    ids_by_board: dict[str, set[str]] = {}
    for spec_path in board_specs:
        spec = load_json(spec_path)
        board_id = spec.get("id")
        if not board_id:
            continue
        key_objects = spec.get("keyObjects", [])
        ids_by_board[board_id] = {obj["id"] for obj in key_objects if isinstance(obj, dict) and "id" in obj}
    return ids_by_board


def find_closest_id(target: str, candidates: set[str]) -> str | None:
    if target in candidates:
        return target
    target_lower = target.lower().replace("_", "")
    candidates_lower = {c: c.lower().replace("_", "") for c in candidates}
    for c, lowered in candidates_lower.items():
        if lowered == target_lower:
            return c
    best: str | None = None
    best_score = 0
    for c, lowered in candidates_lower.items():
        score = 0
        if target_lower in lowered or lowered in target_lower:
            score = max(len(target_lower), len(lowered))
        if score > best_score:
            best_score = score
            best = c
    return best


def validate_alignment(
    voiceover: dict[str, Any],
    ids_by_board: dict[str, set[str]],
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    aligned = 0

    for segment in voiceover.get("segments", []):
        board_id = segment.get("boardId")
        target = segment.get("targetElement")
        if not board_id or not target:
            continue
        candidates = ids_by_board.get(board_id, set())
        if target in candidates:
            aligned += 1
            continue

        suggestion = find_closest_id(target, candidates)
        mismatches.append(
            {
                "segmentId": segment.get("id"),
                "boardId": board_id,
                "targetElement": target,
                "suggestedMatch": suggestion,
                "availableIds": sorted(candidates),
                "message": (
                    f"B 脚本引用了 '{target}'，但 board_spec 中只有 "
                    f"{', '.join(sorted(candidates))}，建议映射为 '{suggestion}'"
                    if suggestion
                    else f"B 脚本引用了 '{target}'，但 board_spec 中没有任何接近的 ID"
                ),
            }
        )

    total = aligned + len(mismatches)
    status = "PASS" if not mismatches else "WARN"
    return {
        "schemaVersion": 1,
        "generatedAt": None,
        "status": status,
        "summary": {
            "totalTargets": total,
            "aligned": aligned,
            "mismatches": len(mismatches),
        },
        "mismatches": mismatches,
    }


def discover_board_specs(project_dir: Path) -> list[Path]:
    candidates = [
        project_dir / "infographic" / "board_specs",
        project_dir / "board_specs",
    ]
    specs: list[Path] = []
    for directory in candidates:
        if directory.is_dir():
            specs.extend(sorted(directory.glob("*.board_spec.json")))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Align B voiceover targetElement IDs with C board_spec keyObjects."
    )
    parser.add_argument("--project-dir", type=Path, help="Project root containing script/ and infographic/")
    parser.add_argument("--voiceover", type=Path, help="Path to voiceover_segments.json")
    parser.add_argument("--board-specs-dir", type=Path, help="Directory with *.board_spec.json files")
    parser.add_argument("--output", type=Path, help="Path to write cross_stage_validation_report.json")
    args = parser.parse_args()

    if args.project_dir:
        voiceover_path = args.voiceover or args.project_dir / "script" / "voiceover_segments.json"
        board_specs = discover_board_specs(args.project_dir)
        output_path = args.output or args.project_dir / "cross_stage_validation_report.json"
    elif args.voiceover and args.board_specs_dir:
        voiceover_path = args.voiceover
        board_specs = sorted(args.board_specs_dir.glob("*.board_spec.json"))
        output_path = args.output or Path("cross_stage_validation_report.json")
    else:
        print(
            "ERROR: provide --project-dir or both --voiceover and --board-specs-dir",
            file=sys.stderr,
        )
        return 2

    if not voiceover_path.is_file():
        print(f"ERROR: voiceover not found: {voiceover_path}", file=sys.stderr)
        return 2

    voiceover = load_json(voiceover_path)
    ids_by_board = collect_key_object_ids(board_specs)
    report = validate_alignment(voiceover, ids_by_board)
    report["generatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Cross-stage validation: {report['status']}")
    print(f"- total targets: {report['summary']['totalTargets']}")
    print(f"- aligned: {report['summary']['aligned']}")
    print(f"- mismatches: {report['summary']['mismatches']}")
    for mismatch in report["mismatches"]:
        print(f"WARNING: {mismatch['message']}")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
