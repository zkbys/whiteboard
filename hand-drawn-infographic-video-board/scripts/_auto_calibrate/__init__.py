"""Auto-calibration helpers for whiteboard board images."""

from __future__ import annotations

from .backends import (
    CalibrationBackend,
    DetectedElement,
    MockBackend,
    OcrBackend,
    VlmBackend,
    resolve_backend,
)
from .geometry import build_calibrated_element
from .matching import match_candidates

__all__ = [
    "CalibrationBackend",
    "DetectedElement",
    "MockBackend",
    "OcrBackend",
    "VlmBackend",
    "build_calibrated_element",
    "match_candidates",
    "resolve_backend",
]
