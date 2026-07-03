#!/usr/bin/env python3
"""Extract start/done keyframes for annotation actions in a motion plan."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "item"


def time_name(value: float) -> str:
    return f"{value:.3f}".replace(".", "p")


def run_ffmpeg(ffmpeg: str, video: Path, timestamp: float, output: Path) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-ss",
            f"{max(0, timestamp):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def collect_rows(plan: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index = 1
    for segment in plan.get("segments", []):
        segment_start = float(segment.get("start", 0))
        for action in segment.get("actions", []):
            draw_start = segment_start + float(action.get("offset", 0))
            draw_done = draw_start + float(action.get("duration", 0))
            base = (
                f"{index:02d}-"
                f"{safe_name(str(segment.get('id', 'segment')))}-"
                f"{safe_name(str(action.get('annotation', action.get('type', 'annotation'))))}"
            )
            start_file = out_dir / f"{base}-start-t{time_name(draw_start)}.jpg"
            done_file = out_dir / f"{base}-done-t{time_name(draw_done)}.jpg"
            rows.append(
                {
                    "index": index,
                    "segment": segment.get("id"),
                    "annotation": action.get("annotation"),
                    "type": action.get("type"),
                    "element": action.get("element"),
                    "spokenAnchor": action.get("spokenAnchor"),
                    "drawStart": round(draw_start, 3),
                    "drawDone": round(draw_done, 3),
                    "startFrame": str(start_file),
                    "doneFrame": str(done_file),
                }
            )
            index += 1
    return rows


def build_contact_sheet(ffmpeg: str, out_dir: Path, pattern: str, output: Path, columns: int) -> None:
    matches = sorted(out_dir.glob(pattern))
    if not matches:
        return
    tile = f"{columns}x{max(1, (len(matches) + columns - 1) // columns)}"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-pattern_type",
            "glob",
            "-i",
            str(out_dir / pattern),
            "-vf",
            f"scale=480:-1,tile={tile}:padding=8:margin=8:color=white",
            "-q:v",
            "2",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, help="Rendered video path. Required unless --manifest-only is set.")
    parser.add_argument("--motion-plan", required=True, type=Path, help="motion_plan.json")
    parser.add_argument("--output", required=True, type=Path, help="Output keyframe directory")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg binary")
    parser.add_argument("--manifest-only", action="store_true", help="Write timestamp manifest without extracting images")
    parser.add_argument("--contact-sheet", action="store_true", help="Also build start/done contact sheets")
    parser.add_argument("--columns", type=int, default=4, help="Contact sheet columns")
    args = parser.parse_args()

    if not args.manifest_only and not args.video:
        raise SystemExit("--video is required unless --manifest-only is set")
    if args.video and not args.video.exists():
        raise SystemExit(f"video not found: {args.video}")

    plan = read_json(args.motion_plan)
    args.output.mkdir(parents=True, exist_ok=True)
    rows = collect_rows(plan, args.output)

    if not args.manifest_only:
        for row in rows:
            run_ffmpeg(args.ffmpeg, args.video, row["drawStart"], Path(row["startFrame"]))
            run_ffmpeg(args.ffmpeg, args.video, row["drawDone"], Path(row["doneFrame"]))
        if args.contact_sheet:
            build_contact_sheet(args.ffmpeg, args.output, "*-start-*.jpg", args.output / "contact_sheet_start.jpg", args.columns)
            build_contact_sheet(args.ffmpeg, args.output, "*-done-*.jpg", args.output / "contact_sheet_done.jpg", args.columns)

    write_json(args.output / "keyframe_manifest.json", rows)
    print(json.dumps({"outDir": str(args.output), "actions": len(rows), "frames": len(rows) * (0 if args.manifest_only else 2)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
