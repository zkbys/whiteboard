"""Detection backends for auto-calibration.

Backends take a board image path plus a list of candidate elements and return a
list of detected text boxes with confidence scores.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DetectedElement:
    text: str
    bbox: list[float]  # [x, y, width, height]
    confidence: float


class CalibrationBackend(ABC):
    """Abstract base for element detection backends."""

    name: str = "abstract"

    @abstractmethod
    def detect(self, image_path: Path, candidates: list[dict[str, Any]]) -> list[DetectedElement]:
        """Return detected text boxes for the given image."""
        ...

    def is_available(self) -> bool:
        """Return True if the backend can be used in the current environment."""
        return True


class MockBackend(CalibrationBackend):
    """Deterministic backend for tests and dry runs.

    Produces fake bboxes distributed in a grid based on candidate labels.
    Does not read the actual image.
    """

    name = "mock"

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    def is_available(self) -> bool:
        return True

    def detect(self, image_path: Path, candidates: list[dict[str, Any]]) -> list[DetectedElement]:
        count = max(1, len(candidates))
        cols = max(1, int(count**0.5))
        cell_w = 1600 / cols
        cell_h = 900 / max(1, (count + cols - 1) // cols)
        results: list[DetectedElement] = []
        for index, candidate in enumerate(candidates):
            label = str(candidate.get("label") or candidate.get("text") or candidate.get("id", ""))
            col = index % cols
            row = index // cols
            x = 200 + col * cell_w + (index % 3) * 20
            y = 100 + row * cell_h + (index % 5) * 15
            w = max(120, min(cell_w * 0.8, 60 + len(label) * 28))
            h = max(50, cell_h * 0.5)
            results.append(
                DetectedElement(
                    text=label,
                    bbox=[round(x, 2), round(y, 2), round(w, 2), round(h, 2)],
                    confidence=0.95,
                )
            )
        return results


class VlmBackend(CalibrationBackend):
    """Vision-LM backend using an OpenAI-compatible chat completions endpoint.

    The model is asked to return a JSON object with detected element bboxes.
    No API key is persisted; it is read from the configured environment variable.
    """

    name = "vlm"

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(os.environ.get(self.api_key_env))

    def _encode_image(self, image_path: Path) -> str:
        data = image_path.read_bytes()
        return base64.b64encode(data).decode("utf-8")

    def _build_prompt(self, candidates: list[dict[str, Any]]) -> str:
        labels = "\n".join(
            f'- {cand.get("id")}: {cand.get("label") or cand.get("text") or cand.get("id")}'
            for cand in candidates
        )
        return (
            "You are a layout analyzer for a whiteboard explainer video. "
            "Detect the following text elements in the image and return their "
            "pixel bounding boxes in the image coordinate system.\n\n"
            f"Elements to find:\n{labels}\n\n"
            "Return ONLY a JSON object in this exact format:\n"
            '{"elements": [{"text": "exact text", "bbox": [x, y, width, height], "confidence": 0.95}]}\n'
            "Use integer pixel coordinates. If an element is not found, omit it."
        )

    def detect(self, image_path: Path, candidates: list[dict[str, Any]]) -> list[DetectedElement]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"VLM backend requires {self.api_key_env} environment variable")

        b64_image = self._encode_image(image_path)
        prompt = self._build_prompt(candidates)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"VLM API error: {exc.code} {body}") from exc

        content = (
            result.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        return self._parse_response(content)

    @staticmethod
    def _parse_response(content: str) -> list[DetectedElement]:
        """Parse a JSON response that may be wrapped in markdown fences."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        data = json.loads(text)
        elements = data.get("elements", []) if isinstance(data, dict) else []
        results: list[DetectedElement] = []
        for item in elements:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            results.append(
                DetectedElement(
                    text=str(item.get("text", "")),
                    bbox=[float(v) for v in bbox],
                    confidence=float(item.get("confidence", 0.8)),
                )
            )
        return results

    def dry_run_info(self, image_path: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the prompt and image size without calling the API."""
        return {
            "model": self.model,
            "baseUrl": self.base_url,
            "imageBytes": image_path.stat().st_size if image_path.exists() else 0,
            "candidateCount": len(candidates),
            "prompt": self._build_prompt(candidates),
        }


class OcrBackend(CalibrationBackend):
    """Local OCR backend using easyocr or paddleocr.

    Installs are optional; the backend probes import availability at runtime.
    """

    name = "ocr"

    def __init__(self, backend: str = "auto") -> None:
        self.preferred = backend
        self._reader: Any | None = None
        self._impl: str | None = None

    def is_available(self) -> bool:
        return self._detect_impl() is not None

    def _detect_impl(self) -> str | None:
        if self._impl:
            return self._impl
        order = [self.preferred] if self.preferred and self.preferred != "auto" else ["easyocr", "paddleocr"]
        for name in order:
            try:
                __import__(name)
                self._impl = name
                return name
            except ImportError:
                continue
        return None

    def _get_reader(self) -> Any:
        if self._reader is not None:
            return self._reader
        impl = self._detect_impl()
        if impl == "easyocr":
            import easyocr  # type: ignore[import-untyped]

            self._reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        elif impl == "paddleocr":
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            self._reader = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        else:
            raise RuntimeError(
                "No OCR backend available. Install easyocr (pip install easyocr) "
                "or paddleocr (pip install paddleocr), or use --provider vlm."
            )
        return self._reader

    def detect(self, image_path: Path, candidates: list[dict[str, Any]]) -> list[DetectedElement]:
        impl = self._detect_impl()
        if impl == "easyocr":
            return self._detect_easyocr(image_path)
        if impl == "paddleocr":
            return self._detect_paddleocr(image_path)
        raise RuntimeError("No OCR backend available.")

    def _detect_easyocr(self, image_path: Path) -> list[DetectedElement]:
        reader = self._get_reader()
        results = reader.readtext(str(image_path))
        detected: list[DetectedElement] = []
        for bbox, text, conf in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x, y = min(xs), min(ys)
            w, h = max(xs) - x, max(ys) - y
            detected.append(
                DetectedElement(text=text, bbox=[round(x, 2), round(y, 2), round(w, 2), round(h, 2)], confidence=round(conf, 3))
            )
        return detected

    def _detect_paddleocr(self, image_path: Path) -> list[DetectedElement]:
        reader = self._get_reader()
        results = reader.ocr(str(image_path), cls=True)
        detected: list[DetectedElement] = []
        for line in results or []:
            for item in line:
                bbox, (text, conf) = item
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                x, y = min(xs), min(ys)
                w, h = max(xs) - x, max(ys) - y
                detected.append(
                    DetectedElement(text=text, bbox=[round(x, 2), round(y, 2), round(w, 2), round(h, 2)], confidence=round(conf, 3))
                )
        return detected


class AgentBackend(CalibrationBackend):
    """Claude/Anthropic Messages API backend for whiteboard element detection.

    Uses the Anthropic Messages API with a vision prompt. The API key is read
    from the configured environment variable at request time and is never
    persisted or logged.
    """

    name = "agent"

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        api_key_env: str = "ANTHROPIC_AUTH_TOKEN",
        base_url_env: str = "ANTHROPIC_BASE_URL",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = (os.environ.get(base_url_env) or "https://api.anthropic.com").rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(os.environ.get(self.api_key_env))

    def _encode_image(self, image_path: Path) -> str:
        data = image_path.read_bytes()
        return base64.b64encode(data).decode("utf-8")

    def _build_prompt(self, candidates: list[dict[str, Any]]) -> str:
        labels = "\n".join(
            f'- {cand.get("id")}: {cand.get("label") or cand.get("text") or cand.get("id")}'
            for cand in candidates
        )
        return (
            "You are a precise layout analyzer for a hand-drawn whiteboard explainer video. "
            "Detect the following text elements in the image and return their pixel bounding "
            "boxes in the image coordinate system.\n\n"
            f"Elements to find:\n{labels}\n\n"
            "First, briefly describe each element you see and where it is located. Then "
            "return ONLY a JSON object in this exact format:\n"
            '{"elements": [{"text": "exact text", "bbox": [x, y, width, height], "confidence": 0.95}]}\n'
            "Use integer pixel coordinates. If an element is not found, omit it."
        )

    def detect(self, image_path: Path, candidates: list[dict[str, Any]]) -> list[DetectedElement]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Agent backend requires {self.api_key_env} environment variable")

        b64_image = self._encode_image(image_path)
        prompt = self._build_prompt(candidates)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_image,
                            },
                        },
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Anthropic API error: {exc.code} {body}") from exc

        content = result.get("content", [])
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")
        return self._parse_response(text)

    @staticmethod
    def _parse_response(content: str) -> list[DetectedElement]:
        """Parse a JSON response that may contain CoT text before a JSON block."""
        text = content.strip()
        # If the response ends with a fenced JSON block, extract it.
        if "```" in text:
            parts = text.rsplit("```", 1)
            # parts[-1] is after the last fence; if empty, the fence enclosed JSON.
            candidate = parts[-2] if len(parts) > 1 and not parts[-1].strip() else text
            # Find the last opening fence and take what follows it.
            if "```" in candidate:
                _, fenced = candidate.rsplit("```", 1)
                text = fenced.strip()
            else:
                text = text.rsplit("```", 1)[0].strip()

        # Fall back to finding the last JSON object in the text.
        if not text.startswith("{"):
            start = text.rfind("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end < start:
                raise ValueError("No JSON object found in agent response")
            text = text[start : end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agent response is not valid JSON: {exc}") from exc

        elements = data.get("elements", []) if isinstance(data, dict) else []
        results: list[DetectedElement] = []
        for item in elements:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            results.append(
                DetectedElement(
                    text=str(item.get("text", "")),
                    bbox=[float(v) for v in bbox],
                    confidence=float(item.get("confidence", 0.8)),
                )
            )
        return results

    def dry_run_info(self, image_path: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the prompt and image size without calling the API."""
        return {
            "model": self.model,
            "baseUrl": self.base_url,
            "imageBytes": image_path.stat().st_size if image_path.exists() else 0,
            "candidateCount": len(candidates),
            "prompt": self._build_prompt(candidates),
        }


def resolve_backend(provider: str, **kwargs: Any) -> CalibrationBackend:
    """Resolve a provider string to a backend instance."""
    provider = provider.lower().strip()
    if provider == "mock":
        return MockBackend()
    if provider == "vlm":
        return VlmBackend(
            model=kwargs.get("vlm_model", "gpt-4o"),
            base_url=kwargs.get("vlm_base_url"),
            api_key_env=kwargs.get("api_key_env", "OPENAI_API_KEY"),
            timeout=float(kwargs.get("timeout", 120.0)),
        )
    if provider in {"agent", "claude"}:
        return AgentBackend(
            model=kwargs.get("agent_model", "claude-opus-4-8"),
            api_key_env=kwargs.get("agent_api_key_env", "ANTHROPIC_AUTH_TOKEN"),
            base_url_env=kwargs.get("agent_base_url_env", "ANTHROPIC_BASE_URL"),
            timeout=float(kwargs.get("timeout", 120.0)),
        )
    if provider == "ocr":
        return OcrBackend(backend=kwargs.get("ocr_backend", "auto"))
    raise ValueError(f"Unknown calibration provider: {provider}")
