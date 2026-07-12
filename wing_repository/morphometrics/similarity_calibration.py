"""Empirical similarity-percentile calibration for nearest-shape distances."""

from __future__ import annotations

import numpy as np


def empirical_similarity_percentile(
    distance: float,
    calibration_distances: np.ndarray | list[float],
) -> float:
    """Return an empirical percentile where smaller distance is more similar.

    This intentionally does not use ``100 * (1 - distance)``.  The percentile is
    the percentage of reference calibration distances that are greater than or
    equal to the query distance.
    """

    values = np.asarray(calibration_distances, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("A finite one-dimensional calibration distribution is required.")
    if not np.isfinite(distance) or distance < 0:
        raise ValueError("Distance must be a finite non-negative value.")
    return float(100.0 * np.mean(values >= distance))


def pairwise_reference_distance_distribution(aligned_shapes: np.ndarray) -> np.ndarray:
    """Return all upper-triangle pairwise distances among aligned references."""

    shapes = np.asarray(aligned_shapes, dtype=np.float64)
    if shapes.ndim != 3 or shapes.shape[0] < 2 or shapes.shape[1:] != (19, 2):
        raise ValueError("At least two aligned 19-landmark shapes are required.")
    distances: list[float] = []
    for first in range(shapes.shape[0]):
        for second in range(first + 1, shapes.shape[0]):
            distances.append(float(np.linalg.norm(shapes[first] - shapes[second])))
    return np.asarray(distances, dtype=np.float64)


__all__ = [
    "empirical_similarity_percentile",
    "pairwise_reference_distance_distribution",
]
