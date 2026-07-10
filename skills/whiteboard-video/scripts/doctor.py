#!/usr/bin/env python3
"""Run the bundled whiteboard-video doctor from either source or an installation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    marker_path = skill_root / "installation.json"
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"DOCTOR FAIL: cannot read {marker_path}: {exc}", file=sys.stderr)
            return 2
        runtime_root = (skill_root / str(marker.get("runtime", "runtime"))).resolve()
    else:
        runtime_root = skill_root.parents[1]

    doctor = runtime_root / "scripts" / "doctor.py"
    if not doctor.is_file():
        print(f"DOCTOR FAIL: bundled doctor not found: {doctor}", file=sys.stderr)
        return 2
    command = [
        sys.executable,
        str(doctor),
        "--runtime-root",
        str(runtime_root),
        "--skill-root",
        str(skill_root),
        *sys.argv[1:],
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
