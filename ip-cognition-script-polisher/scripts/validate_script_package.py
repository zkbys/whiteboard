#!/usr/bin/env python3
"""Validate an ip-cognition-script-polisher output package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_ROLES = ["hook", "反常识", "例子", "转折", "方法", "结论"]
REQUIRED_SEGMENT_FIELDS = ["id", "role", "text", "caption", "visualIntent", "spokenAnchors"]
REQUIRED_VOICEOVER_FIELDS = ["topic", "style", "targetDurationSec", "segments"]
REQUIRED_VISUAL_FIELDS = ["topic", "visualStyle", "beats"]
REQUIRED_BEAT_FIELDS = [
    "id",
    "sourceSegmentId",
    "boardId",
    "visualIntent",
    "spokenAnchors",
    "keyObjects",
]


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_json(path: Path, report: ValidationReport) -> Any:
    if not path.exists():
        report.error(f"Missing file: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"Invalid JSON in {path}: {exc}")
        return None


def text_units(text: str) -> float:
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9+._/-]*", text))
    return cjk + words * 1.8


def estimate_segment_duration(segment: dict[str, Any], chars_per_sec: float) -> float:
    text = str(segment.get("text", ""))
    pause = segment.get("pauseAfter", 0.18)
    try:
        pause_value = max(0.0, float(pause))
    except (TypeError, ValueError):
        pause_value = 0.18
    return text_units(text) / chars_per_sec + pause_value


def validate_anchor_list(
    owner: str,
    anchors: Any,
    text: str,
    caption: str,
    report: ValidationReport,
) -> None:
    if not isinstance(anchors, list) or not anchors:
        report.error(f"{owner}: spokenAnchors must be a non-empty array")
        return
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, str) or not anchor.strip():
            report.error(f"{owner}: spokenAnchors[{index}] must be a non-empty string")
            continue
        if anchor not in text and anchor not in caption:
            report.error(f"{owner}: spokenAnchor does not appear in text/caption: {anchor!r}")


def validate_voiceover(data: Any, report: ValidationReport, chars_per_sec: float) -> tuple[dict[str, Any], float]:
    if not isinstance(data, dict):
        report.error("voiceover_segments.json must be a JSON object")
        return {}, 0.0

    for field in REQUIRED_VOICEOVER_FIELDS:
        if field not in data:
            report.error(f"voiceover_segments.json missing top-level field: {field}")

    target_duration = data.get("targetDurationSec")
    if not isinstance(target_duration, (int, float)):
        report.error("targetDurationSec must be a number")

    segments = data.get("segments")
    if not isinstance(segments, list):
        report.error("segments must be an array")
        return {}, 0.0

    if len(segments) != len(REQUIRED_ROLES):
        report.error(f"segments must contain exactly {len(REQUIRED_ROLES)} items")

    ids: set[str] = set()
    seen_roles: list[str] = []
    segment_map: dict[str, Any] = {}
    total_duration = 0.0

    for index, segment in enumerate(segments):
        owner = f"segments[{index}]"
        if not isinstance(segment, dict):
            report.error(f"{owner} must be an object")
            continue

        for field in REQUIRED_SEGMENT_FIELDS:
            if field not in segment:
                report.error(f"{owner} missing field: {field}")

        segment_id = segment.get("id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            report.error(f"{owner}.id must be a non-empty string")
        elif segment_id in ids:
            report.error(f"{owner}.id is duplicated: {segment_id}")
        else:
            ids.add(segment_id)
            segment_map[segment_id] = segment

        role = segment.get("role")
        if isinstance(role, str):
            seen_roles.append(role)
        else:
            report.error(f"{owner}.role must be a string")

        text = segment.get("text")
        caption = segment.get("caption")
        visual_intent = segment.get("visualIntent")
        if not isinstance(text, str) or not text.strip():
            report.error(f"{owner}.text must be a non-empty string")
            text = ""
        if not isinstance(caption, str) or not caption.strip():
            report.error(f"{owner}.caption must be a non-empty string")
            caption = ""
        if not isinstance(visual_intent, str) or not visual_intent.strip():
            report.error(f"{owner}.visualIntent must be a non-empty string")

        validate_anchor_list(owner, segment.get("spokenAnchors"), text, caption, report)
        total_duration += estimate_segment_duration(segment, chars_per_sec)

    if seen_roles != REQUIRED_ROLES:
        report.error(f"segment roles must be exactly {REQUIRED_ROLES}; got {seen_roles}")

    declared_estimate = data.get("estimatedDurationSec")
    if isinstance(declared_estimate, (int, float)) and abs(float(declared_estimate) - total_duration) > 3:
        report.warn(
            f"estimatedDurationSec differs from validator estimate by more than 3s: "
            f"declared={declared_estimate}, validator={total_duration:.2f}"
        )

    return segment_map, total_duration


def validate_visual_beats(data: Any, segment_map: dict[str, Any], report: ValidationReport) -> None:
    if not isinstance(data, dict):
        report.error("visual_beats.json must be a JSON object")
        return

    for field in REQUIRED_VISUAL_FIELDS:
        if field not in data:
            report.error(f"visual_beats.json missing top-level field: {field}")

    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        report.error("beats must be a non-empty array")
        return

    if len(beats) > 6:
        report.warn("visual_beats.json has more than 6 beats; consider compressing visual ideas")

    beat_ids: set[str] = set()
    for index, beat in enumerate(beats):
        owner = f"beats[{index}]"
        if not isinstance(beat, dict):
            report.error(f"{owner} must be an object")
            continue

        for field in REQUIRED_BEAT_FIELDS:
            if field not in beat:
                report.error(f"{owner} missing field: {field}")

        beat_id = beat.get("id")
        if not isinstance(beat_id, str) or not beat_id.strip():
            report.error(f"{owner}.id must be a non-empty string")
        elif beat_id in beat_ids:
            report.error(f"{owner}.id is duplicated: {beat_id}")
        else:
            beat_ids.add(beat_id)

        source_id = beat.get("sourceSegmentId")
        if not isinstance(source_id, str) or source_id not in segment_map:
            report.error(f"{owner}.sourceSegmentId must match a voiceover segment id")
            source_segment = {}
        else:
            source_segment = segment_map[source_id]

        visual_intent = beat.get("visualIntent")
        if not isinstance(visual_intent, str) or not visual_intent.strip():
            report.error(f"{owner}.visualIntent must be a non-empty string")

        key_objects = beat.get("keyObjects")
        if not isinstance(key_objects, list) or not key_objects:
            report.error(f"{owner}.keyObjects must be a non-empty array")
        else:
            for object_index, key_object in enumerate(key_objects):
                if not isinstance(key_object, dict):
                    report.error(f"{owner}.keyObjects[{object_index}] must be an object")
                    continue
                for field in ["id", "label", "role"]:
                    if not isinstance(key_object.get(field), str) or not key_object.get(field, "").strip():
                        report.error(f"{owner}.keyObjects[{object_index}].{field} must be a non-empty string")

        text = str(source_segment.get("text", ""))
        caption = str(source_segment.get("caption", ""))
        validate_anchor_list(owner, beat.get("spokenAnchors"), text, caption, report)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an IP cognition script package.")
    parser.add_argument("--package-dir", type=Path, help="Directory containing voiceover_segments.json and visual_beats.json")
    parser.add_argument("--voiceover", type=Path, help="Path to voiceover_segments.json")
    parser.add_argument("--visual-beats", type=Path, help="Path to visual_beats.json")
    parser.add_argument("--min-sec", type=float, default=30.0, help="Minimum estimated duration in seconds")
    parser.add_argument("--max-sec", type=float, default=60.0, help="Maximum estimated duration in seconds")
    parser.add_argument("--chars-per-sec", type=float, default=4.8, help="Estimated Mandarin reading speed")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = ValidationReport()

    if args.package_dir:
        voiceover_path = args.package_dir / "voiceover_segments.json"
        visual_beats_path = args.package_dir / "visual_beats.json"
    else:
        voiceover_path = args.voiceover
        visual_beats_path = args.visual_beats

    if not voiceover_path or not visual_beats_path:
        print("ERROR: provide --package-dir or both --voiceover and --visual-beats", file=sys.stderr)
        return 2

    if args.chars_per_sec <= 0:
        print("ERROR: --chars-per-sec must be positive", file=sys.stderr)
        return 2

    voiceover_data = load_json(voiceover_path, report)
    visual_beats_data = load_json(visual_beats_path, report)

    segment_map, estimated_duration = validate_voiceover(voiceover_data, report, args.chars_per_sec)
    validate_visual_beats(visual_beats_data, segment_map, report)

    if estimated_duration < args.min_sec or estimated_duration > args.max_sec:
        report.error(
            f"estimated duration {estimated_duration:.2f}s is outside allowed range "
            f"{args.min_sec:.2f}-{args.max_sec:.2f}s"
        )

    if isinstance(voiceover_data, dict):
        target_duration = voiceover_data.get("targetDurationSec")
        if isinstance(target_duration, (int, float)) and (target_duration < args.min_sec or target_duration > args.max_sec):
            report.error(
                f"targetDurationSec {target_duration:.2f}s is outside allowed range "
                f"{args.min_sec:.2f}-{args.max_sec:.2f}s"
            )

    print("Script package validation")
    print(f"- voiceover: {voiceover_path}")
    print(f"- visual beats: {visual_beats_path}")
    print(f"- estimated duration: {estimated_duration:.2f}s")

    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")

    if report.ok:
        print("PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

