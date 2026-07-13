#!/usr/bin/env python3
"""Diagnose image provider configuration and API reachability."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose whiteboard-video image provider configuration and API reachability."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead of text."
    )
    parser.add_argument(
        "--probe-size",
        default="1024x1024",
        help="Image size for the probe request (default: 1024x1024).",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="Seconds allowed for the API probe."
    )
    parser.add_argument(
        "--env-file", type=Path, help="Load WHITEBOARD_* and OPENAI_API_KEY from a .env file."
    )
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.is_file():
        print(f"[WARN] env file not found: {path}", file=sys.stderr)
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
        return
    except ImportError:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith("WHITEBOARD_") or key == "OPENAI_API_KEY":
            os.environ.setdefault(key, value)


def provider_status() -> dict[str, Any]:
    mode = os.environ.get("WHITEBOARD_IMAGE_MODE", "interactive").strip().lower()
    provider = os.environ.get("WHITEBOARD_IMAGE_PROVIDER", "").strip().lower()
    api_key_env = os.environ.get("WHITEBOARD_OPENAI_API_KEY_ENV", "OPENAI_API_KEY")

    result: dict[str, Any] = {
        "mode": mode,
        "provider": provider or None,
        "api_key_env": api_key_env,
        "api_key_present": bool(os.environ.get(api_key_env)),
    }

    if mode == "interactive":
        result["login_required"] = False
        result["ready"] = True
        result["message"] = "Interactive mode: no API key needed, but PNGs must be saved manually."
        return result

    if provider == "openai":
        result["login_required"] = True
        result["ready"] = bool(os.environ.get(api_key_env))
        result["model"] = os.environ.get("WHITEBOARD_OPENAI_IMAGE_MODEL", DEFAULT_MODEL)
        result["base_url"] = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        result["message"] = (
            "OpenAI provider configured."
            if result["ready"]
            else f"OpenAI provider requires {api_key_env}."
        )
        return result

    if provider == "command":
        command = os.environ.get("WHITEBOARD_IMAGE_COMMAND", "")
        expanded = str(Path(command).expanduser()) if command else ""
        executable = shutil.which(expanded) if expanded else None
        if not executable and expanded:
            path = Path(expanded)
            if path.is_file() and os.access(path, os.X_OK):
                executable = str(path.resolve())
        result["login_required"] = False
        result["ready"] = bool(executable)
        result["command"] = executable
        result["message"] = (
            "Command provider is executable."
            if executable
            else "Command provider requires executable WHITEBOARD_IMAGE_COMMAND."
        )
        return result

    result["login_required"] = False
    result["ready"] = False
    result["message"] = (
        "Auto mode requires WHITEBOARD_IMAGE_PROVIDER=openai or command."
    )
    return result


def probe_openai(size: str, timeout: float) -> dict[str, Any]:
    api_key_env = os.environ.get("WHITEBOARD_OPENAI_API_KEY_ENV", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        return {"ok": False, "error": f"{api_key_env} is not set"}

    model = os.environ.get("WHITEBOARD_OPENAI_IMAGE_MODEL", DEFAULT_MODEL)
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    payload = {
        "model": model,
        "prompt": "A small hand-drawn whiteboard test square.",
        "n": 1,
        "size": size,
        "quality": "low",
        "output_format": "png",
    }
    request = urllib.request.Request(
        base_url + "/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "whiteboard-video/0.2-test-image-provider",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read(600).decode("utf-8", "replace").replace(api_key, "[REDACTED]")
        return {"ok": False, "error": f"HTTP {exc.code}: {body}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"URL error: {exc.reason}"}
    except TimeoutError:
        return {"ok": False, "error": f"timed out after {timeout:g}s"}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON response: {exc}"}

    images = response_data.get("data")
    first = images[0] if isinstance(images, list) and images and isinstance(images[0], dict) else {}
    encoded = first.get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        return {"ok": False, "error": "response did not contain data[0].b64_json"}
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        return {"ok": False, "error": f"invalid base64: {exc}"}

    if not image_bytes.startswith(b"\x89PNG"):
        return {"ok": False, "error": "decoded bytes are not a PNG"}
    return {"ok": True, "bytes": len(image_bytes), "usage": response_data.get("usage")}


def diagnose(args: argparse.Namespace) -> dict[str, Any]:
    status = provider_status()
    report: dict[str, Any] = {
        "schema_version": 1,
        "provider_status": status,
        "config_advice": (
            "To enable automatic image generation, set:\n"
            "  export WHITEBOARD_IMAGE_MODE=auto\n"
            "  export WHITEBOARD_IMAGE_PROVIDER=openai\n"
            '  export OPENAI_API_KEY="..."'
        ),
    }

    if status.get("provider") == "openai" and status.get("ready"):
        report["probe"] = probe_openai(args.probe_size, args.timeout)
        report["ready"] = report["probe"].get("ok", False)
    else:
        report["probe"] = {"ok": False, "error": "provider not ready or not openai"}
        report["ready"] = status.get("ready", False)

    return report


def print_human(report: dict[str, Any]) -> None:
    status = report["provider_status"]
    print(f"Image mode:       {status['mode']}")
    print(f"Provider:         {status.get('provider') or 'not set'}")
    print(f"Ready:            {report['ready']}")
    print(f"Message:          {status['message']}")
    if "model" in status:
        print(f"Model:            {status['model']}")
    if "command" in status:
        print(f"Command:          {status['command']}")

    probe = report.get("probe", {})
    if probe.get("ok"):
        print(f"Probe:            PASS ({probe.get('bytes')} bytes)")
    else:
        print(f"Probe:            FAIL - {probe.get('error')}")
    print("\n" + report["config_advice"])


def main() -> int:
    args = parse_args()
    env_file = args.env_file or (Path.cwd() / ".env")
    load_env_file(env_file)
    report = diagnose(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
