"""Outlier checks against a saved reference-distance distribution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class OutlierResult:
    """Outlier decision for one query."""

    is_outlier: bool
    nearest_distance: float
    threshold: float


def empirical_outlier_threshold(
    calibration_distances: np.ndarray | list[float],
    *,
    quantile: float = 0.99,
) -> float:
    """Return a model-specific empirical distance threshold."""

    values = np.asarray(calibration_distances, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("A finite calibration distribution is required.")
    if not 0 < quantile < 1:
        raise ValueError("Outlier quantile must be between zero and one.")
    return float(np.quantile(values, quantile))


def detect_outlier(
    nearest_distance: float,
    calibration_distances: np.ndarray | list[float],
    *,
    quantile: float = 0.99,
) -> OutlierResult:
    """Flag a query outside the validated reference distribution."""

    threshold = empirical_outlier_threshold(calibration_distances, quantile=quantile)
    return OutlierResult(
        is_outlier=bool(nearest_distance > threshold),
        nearest_distance=float(nearest_distance),
        threshold=threshold,
    )


__all__ = ["OutlierResult", "detect_outlier", "empirical_outlier_threshold"]
