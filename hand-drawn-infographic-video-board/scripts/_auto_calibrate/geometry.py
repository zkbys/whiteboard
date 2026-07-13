"""Geometry helpers for converting detected bboxes into calibration fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


COMPOSITION_W = 1920
COMPOSITION_H = 1080
DEFAULT_SCALE_MIN = 0.8
DEFAULT_SCALE_MAX = 1.35
DEFAULT_SCALE_SAFETY = 0.85


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def to_list(self) -> list[float]:
        return [round(self.x, 2), round(self.y, 2), round(self.width, 2), round(self.height, 2)]

    @classmethod
    def from_list(cls, value: list[float]) -> "Box":
        if len(value) != 4:
            raise ValueError(f"bbox must be [x, y, width, height], got {value}")
        return cls(float(value[0]), float(value[1]), float(value[2]), float(value[3]))

    def clamp(self, canvas_w: float, canvas_h: float) -> "Box":
        x = max(0.0, min(self.x, canvas_w - 1))
        y = max(0.0, min(self.y, canvas_h - 1))
        width = max(1.0, min(self.width, canvas_w - x))
        height = max(1.0, min(self.height, canvas_h - y))
        return Box(x, y, width, height)


def derive_camera(box: Box, canvas_w: float, canvas_h: float) -> dict[str, float]:
    """Derive a camera framing from a bbox.

    The camera centers on the bbox and scales so the box fits comfortably
    inside the 1920x1080 composition with a safety margin.
    """
    scale_w = COMPOSITION_W / box.width if box.width > 0 else DEFAULT_SCALE_MAX
    scale_h = COMPOSITION_H / box.height if box.height > 0 else DEFAULT_SCALE_MAX
    scale = min(scale_w, scale_h) * DEFAULT_SCALE_SAFETY
    scale = max(DEFAULT_SCALE_MIN, min(DEFAULT_SCALE_MAX, scale))
    return {
        "x": round(box.cx, 2),
        "y": round(box.cy, 2),
        "scale": round(scale, 3),
    }


def derive_cursor(box: Box, annotation_type: str = "underline") -> dict[str, float]:
    """Derive a default cursor landing point inside a bbox.

    For underlines the cursor lands near the bottom-left of the text.
    For circles/boxes it lands near the right edge so the gesture reads left-to-right.
    """
    kind = (annotation_type or "underline").strip().lower()
    if kind in {"circle", "box", "check"}:
        x = box.x + box.width * 0.82
        y = box.y + box.height * 0.55
    else:
        x = box.x + box.width * 0.05
        y = box.y + box.height * 0.82
    return {"x": round(x, 2), "y": round(y, 2)}


def derive_annotation_target(box: Box, annotation_type: str = "underline") -> list[float]:
    """Derive the annotation target bbox from the element bbox.

    For underlines we keep the full width but focus on the lower portion.
    For circles/boxes we slightly expand to make the gesture visible.
    """
    kind = (annotation_type or "underline").strip().lower()
    if kind == "underline":
        target = Box(
            box.x,
            box.y + box.height * 0.72,
            box.width,
            box.height * 0.28,
        )
    elif kind == "circle":
        margin = min(box.width, box.height) * 0.1
        target = Box(
            box.x - margin,
            box.y - margin,
            box.width + margin * 2,
            box.height + margin * 2,
        )
    elif kind == "box":
        margin = min(box.width, box.height) * 0.08
        target = Box(
            box.x - margin,
            box.y - margin,
            box.width + margin * 2,
            box.height + margin * 2,
        )
    else:
        target = box
    return target.to_list()


def build_calibrated_element(
    element_id: str,
    text: str,
    kind: str,
    role: str | None,
    bbox: list[float],
    actions: list[str] | None,
    canvas_w: float,
    canvas_h: float,
) -> dict[str, Any]:
    """Build a single calibrated element record matching D's expected schema."""
    box = Box.from_list(bbox).clamp(canvas_w, canvas_h)
    primary_action = (actions or ["underline"])[0]
    result: dict[str, Any] = {
        "id": element_id,
        "text": text or element_id,
        "kind": kind or role or "element",
    }
    if role:
        result["role"] = role
    result["bbox"] = box.to_list()
    result["annotationTargetBbox"] = derive_annotation_target(box, primary_action)
    result["camera"] = derive_camera(box, canvas_w, canvas_h)
    result["cursor"] = derive_cursor(box, primary_action)
    if actions:
        result["actions"] = actions
    return result
