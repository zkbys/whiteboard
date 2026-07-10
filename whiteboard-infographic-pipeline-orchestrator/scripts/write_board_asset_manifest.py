#!/usr/bin/env python3
"""Write board_asset_manifest.json from manually downloaded model PNGs."""

from __future__ import annotations

import argparse
import json
import struct
from datetime import date
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        signature = handle.read(8)
        if signature != PNG_SIGNATURE:
            raise ValueError(f"Not a PNG file: {path}")
        chunk_length = int.from_bytes(handle.read(4), "big")
        chunk_type = handle.read(4)
        if chunk_type != b"IHDR" or chunk_length < 8:
            raise ValueError(f"PNG missing IHDR chunk: {path}")
        width, height = struct.unpack(">II", handle.read(8))
    if width <= 0 or height <= 0:
        raise ValueError(f"PNG has invalid dimensions: {path}")
    return width, height


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def load_expected_boards(project_dir: Path, plan_path: Path | None) -> list[dict[str, str]]:
    if plan_path is None:
        plan_path = project_dir / "infographic" / "infographic_plan.json"
    if not plan_path.exists():
        return []

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    boards = []
    for board in plan.get("boards", []):
        board_id = board.get("id") or board.get("boardId")
        if not board_id:
            continue
        boards.append({"boardId": str(board_id), "title": str(board.get("title", ""))})
    return boards


def discover_boards_from_images(images_dir: Path) -> list[dict[str, str]]:
    boards = []
    for image_path in sorted(images_dir.glob("*.model-generated.png")):
        board_id = image_path.name.removesuffix(".model-generated.png")
        boards.append({"boardId": board_id, "title": ""})
    return boards


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    project_dir = args.project_dir.expanduser().resolve()
    images_dir = (args.images_dir or project_dir / "images").expanduser().resolve()
    plan_path = args.infographic_plan.expanduser().resolve() if args.infographic_plan else None
    creator_dir = (args.creator_outputs_dir or project_dir / "creator_outputs").expanduser().resolve()
    prompts_dir = (args.imagegen_prompts_dir or project_dir / "imagegen_prompts").expanduser().resolve()

    if not project_dir.exists() or not project_dir.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")
    if not images_dir.exists() or not images_dir.is_dir():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    boards = load_expected_boards(project_dir, plan_path)
    if not boards:
        boards = discover_boards_from_images(images_dir)
    if not boards:
        raise ValueError(f"No boards found from infographic_plan.json or {images_dir}/*.model-generated.png")

    manifest_boards: list[dict[str, Any]] = []
    for board in boards:
        board_id = board["boardId"]
        image_path = images_dir / f"{board_id}.model-generated.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Missing manually downloaded model PNG: {image_path}")
        width, height = read_png_size(image_path)
        if width < args.min_width or height < args.min_height:
            raise ValueError(
                f"{image_path} is {width}x{height}; expected at least {args.min_width}x{args.min_height}."
            )

        prompt_path = prompts_dir / f"{board_id}.imagegen_prompt.txt"
        creator_output = creator_dir / f"{board_id}.creator_output.md"

        asset: dict[str, Any] = {
            "kind": "file",
            "uri": rel(image_path, project_dir),
            "width": width,
            "height": height,
            "sourcePrompt": rel(prompt_path, project_dir),
            "creatorOutput": rel(creator_output, project_dir),
            "previewCheck": args.preview_check,
        }
        missing_refs = []
        if not prompt_path.exists():
            missing_refs.append("sourcePrompt missing")
        if not creator_output.exists():
            missing_refs.append("creatorOutput missing")
        if missing_refs:
            asset["notes"] = missing_refs

        manifest_boards.append(
            {
                "boardId": board_id,
                "title": board.get("title", ""),
                "asset": asset,
            }
        )

    if args.preview_checked:
        generation_notes = [
            "The built-in image generation tool may expose preview images but no stable URL or file path.",
            "User manually downloaded the previews into this run's images directory.",
            "These PNG files are the actual visual layer passed into D/E.",
        ]
    else:
        generation_notes = [
            f"Images were generated and saved directly by {args.mode}.",
            "Every provider output passed PNG signature and dimension validation before D/E.",
            "No preview-only or manual-download asset was substituted for these files.",
        ]

    return {
        "version": "0.1",
        "assetContract": {
            "allowedKinds": ["file", "url", "inline_generation", "svg_preview"],
            "rule": "Only confirmed real model-generated image assets may enter D/E.",
        },
        "generationRun": {
            "mode": args.mode,
            "previewChecked": args.preview_checked,
            "checkedAt": args.checked_at,
            "notes": generation_notes,
        },
        "boards": manifest_boards,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create board_asset_manifest.json from images/*.model-generated.png.")
    parser.add_argument("--project-dir", type=Path, required=True, help="Pipeline project output directory.")
    parser.add_argument("--images-dir", type=Path, help="Directory containing manually downloaded board PNGs. Defaults to project-dir/images.")
    parser.add_argument("--infographic-plan", type=Path, help="Path to infographic_plan.json. Defaults to project-dir/infographic/infographic_plan.json.")
    parser.add_argument("--creator-outputs-dir", type=Path, help="Directory containing board-XX.creator_output.md files.")
    parser.add_argument("--imagegen-prompts-dir", type=Path, help="Directory containing board-XX.imagegen_prompt.txt files.")
    parser.add_argument("--output", type=Path, help="Output manifest path. Defaults to project-dir/board_asset_manifest.json.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing manifest.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the manifest without writing it.")
    parser.add_argument("--min-width", type=int, default=512, help="Minimum PNG width.")
    parser.add_argument("--min-height", type=int, default=512, help="Minimum PNG height.")
    parser.add_argument("--checked-at", default=date.today().isoformat(), help="Date string for generationRun.checkedAt.")
    parser.add_argument(
        "--preview-checked",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether a human confirmed preview-only images before saving them.",
    )
    parser.add_argument(
        "--mode",
        default="built-in image_gen preview with manual download",
        help="Human-readable image generation mode.",
    )
    parser.add_argument(
        "--preview-check",
        default="confirmed model-generated board for this run; not D SVG and not old smoke preview",
        help="Text stored in each asset.previewCheck.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args)
    project_dir = args.project_dir.expanduser().resolve()
    output_path = (args.output or project_dir / "board_asset_manifest.json").expanduser().resolve()

    rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.dry_run:
        print(rendered, end="")
        return 0

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing manifest without --overwrite: {output_path}")
    output_path.write_text(rendered, encoding="utf-8")
    print(f"[PASS] wrote {output_path}")
    print(f"boards: {len(manifest['boards'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
