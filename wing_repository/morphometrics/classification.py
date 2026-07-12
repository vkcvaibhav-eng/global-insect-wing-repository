"""Interpretation labels for morphometric probability outputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wing_repository.morphometrics.validation import validate_probabilities


@dataclass(frozen=True, slots=True)
class ProbabilityResult:
    """One ranked probability result with cautious interpretation wording."""

    rank: int
    label: str
    probability: float
    reference_sample_count: int
    interpretation: str


DEFAULT_INTERPRETATION_THRESHOLDS = {
    "strong": 0.80,
    "moderate": 0.60,
    "weak": 0.40,
}


def interpretation_label(
    probability: float,
    *,
    thresholds: dict[str, float] | None = None,
    outlier: bool = False,
) -> str:
    """Return a model-specific display label for one probability."""

    if outlier:
        return "Outside validated reference distribution"
    config = thresholds or DEFAULT_INTERPRETATION_THRESHOLDS
    if probability >= config["strong"]:
        return "Strong wing-shape support"
    if probability >= config["moderate"]:
        return "Moderate wing-shape support"
    if probability >= config["weak"]:
        return "Weak wing-shape support"
    return "Inconclusive"


def ranked_probability_results(
    labels: list[str] | tuple[str, ...],
    probabilities: list[float] | np.ndarray,
    sample_counts: dict[str, int],
    *,
    thresholds: dict[str, float] | None = None,
    outlier: bool = False,
) -> list[ProbabilityResult]:
    """Return probability rows sorted high-to-low."""

    values = np.asarray(probabilities, dtype=np.float64)
    validate_probabilities(values, tolerance=1e-5)
    order = np.argsort(-values)
    return [
        ProbabilityResult(
            rank=index + 1,
            label=str(labels[position]),
            probability=float(values[position]),
            reference_sample_count=int(sample_counts.get(str(labels[position]), 0)),
            interpretation=interpretation_label(
                float(values[position]),
                thresholds=thresholds,
                outlier=outlier and index == 0,
            ),
        )
        for index, position in enumerate(order)
    ]


__all__ = [
    "DEFAULT_INTERPRETATION_THRESHOLDS",
    "ProbabilityResult",
    "interpretation_label",
    "ranked_probability_results",
]
