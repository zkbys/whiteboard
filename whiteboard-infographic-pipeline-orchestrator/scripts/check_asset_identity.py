#!/usr/bin/env python3
"""Check that manifest PNGs, D board PNGs, and HyperFrames board PNGs match."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_path(project_dir: Path, manifest_path: Path, uri: str) -> Path:
    raw = Path(uri)
    if raw.is_absolute():
        return raw
    candidates = [
        manifest_path.parent / raw,
        project_dir / raw,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def check_file(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        errors.append(f"missing {label}: {path}")
        return {"label": label, "path": str(path), "exists": False}
    return {
        "label": label,
        "path": str(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def run_check(args: argparse.Namespace) -> dict[str, Any]:
    project_dir = args.project_dir.expanduser().resolve()
    manifest_path = (args.manifest or project_dir / "board_asset_manifest.json").expanduser().resolve()
    board_root = (args.board_root or project_dir / "board_source_for_e").expanduser().resolve()
    hyperframes_board_root = (
        args.hyperframes_board_root or project_dir / "video" / "hyperframes" / "assets" / "boards"
    ).expanduser().resolve()

    errors: list[str] = []
    warnings: list[str] = []

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for board in manifest.get("boards", []):
        board_id = board.get("boardId")
        asset = board.get("asset", {})
        if not board_id:
            errors.append("manifest board missing boardId")
            continue
        if asset.get("kind") != "file":
            errors.append(f"{board_id}: asset.kind must be file for identity check, got {asset.get('kind')!r}")
            continue
        if not asset.get("uri"):
            errors.append(f"{board_id}: asset.uri missing")
            continue

        source = asset_path(project_dir, manifest_path, asset["uri"])
        d_board = board_root / board_id / "board.png"
        hf_board = hyperframes_board_root / board_id / "board.png"

        board_errors: list[str] = []
        files = [
            check_file(source, "manifest", board_errors),
            check_file(d_board, "d_board", board_errors),
        ]
        if args.stage == "all":
            files.append(check_file(hf_board, "hyperframes", board_errors))

        hashes = [file_info.get("sha256") for file_info in files if file_info.get("exists")]
        identical = bool(hashes) and len(set(hashes)) == 1 and not board_errors
        if not identical:
            errors.extend(f"{board_id}: {message}" for message in board_errors)
            if not board_errors:
                errors.append(f"{board_id}: file hashes differ")

        result = {
            "boardId": board_id,
            "identical": identical,
            "files": files,
        }
        results.append(result)

    if not results:
        errors.append("manifest contains no boards")

    return {
        "ok": not errors,
        "projectDir": str(project_dir),
        "manifest": str(manifest_path),
        "boardRoot": str(board_root),
        "hyperframesBoardRoot": str(hyperframes_board_root),
        "stage": args.stage,
        "boards": results,
        "warnings": warnings,
        "errors": errors,
    }


def print_text_report(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"[{status}] asset identity check")
    print(f"manifest: {report['manifest']}")
    print(f"boardRoot: {report['boardRoot']}")
    if report["stage"] == "all":
        print(f"hyperframesBoardRoot: {report['hyperframesBoardRoot']}")
    for board in report["boards"]:
        board_status = "identical" if board["identical"] else "DIFF"
        print(f"- {board['boardId']}: {board_status}")
        for file_info in board["files"]:
            if file_info.get("exists"):
                print(f"  {file_info['label']}: {file_info['sha256'][:16]} {file_info['path']}")
            else:
                print(f"  {file_info['label']}: missing {file_info['path']}")
    if report["errors"]:
        print("\nerrors:")
        for error in report["errors"]:
            print(f"- {error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify board image identity across manifest, D package, and HyperFrames.")
    parser.add_argument("--project-dir", type=Path, required=True, help="Pipeline project output directory.")
    parser.add_argument("--manifest", type=Path, help="Path to board_asset_manifest.json.")
    parser.add_argument("--board-root", type=Path, help="D board package root. Defaults to project-dir/board_source_for_e.")
    parser.add_argument(
        "--hyperframes-board-root",
        type=Path,
        help="HyperFrames boards root. Defaults to project-dir/video/hyperframes/assets/boards.",
    )
    parser.add_argument("--stage", choices=["d", "all"], default="all", help="Use 'd' before E exists, or 'all' after E.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_check(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
