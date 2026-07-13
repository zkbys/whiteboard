"""Text matching between detected elements and board-spec candidates."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Protocol


class SimilarityScorer(Protocol):
    def __call__(self, a: str, b: str) -> float: ...


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def default_scorer(a: str, b: str) -> float:
    """Default text similarity based on SequenceMatcher."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def match_candidates(
    detected: list[dict[str, object]],
    candidates: list[dict[str, object]],
    *,
    min_confidence: float = 0.6,
    scorer: SimilarityScorer | None = None,
) -> list[dict[str, object]]:
    """Match spec candidates to detected text boxes.

    Args:
        detected: list of detected elements, each with at least "text" and "bbox".
        candidates: list of spec elements, each with at least "id" and "label".
        min_confidence: minimum similarity score to accept a match.
        scorer: optional similarity function returning 0..1.

    Returns:
        A list of match records:
        {
            "id": candidate id,
            "matched": bool,
            "detectedText": str,
            "bbox": [x, y, w, h],
            "confidence": float,
            "candidate": original candidate dict,
        }
    """
    scorer = scorer or default_scorer
    results: list[dict[str, object]] = []
    consumed: set[int] = set()

    for candidate in candidates:
        candidate_id = str(candidate.get("id", ""))
        candidate_label = str(candidate.get("label") or candidate.get("text") or candidate_id)

        best_index = -1
        best_score = 0.0
        best_text = ""

        for index, det in enumerate(detected):
            if index in consumed:
                continue
            det_text = str(det.get("text", ""))
            score = scorer(candidate_label, det_text)
            if score > best_score:
                best_score = score
                best_index = index
                best_text = det_text

        if best_index >= 0 and best_score >= min_confidence:
            consumed.add(best_index)
            det = detected[best_index]
            results.append(
                {
                    "id": candidate_id,
                    "matched": True,
                    "detectedText": best_text,
                    "bbox": det.get("bbox"),
                    "confidence": round(best_score, 3),
                    "candidate": candidate,
                }
            )
        else:
            results.append(
                {
                    "id": candidate_id,
                    "matched": False,
                    "detectedText": best_text if best_index >= 0 else "",
                    "confidence": round(best_score, 3),
                    "candidate": candidate,
                }
            )

    return results
