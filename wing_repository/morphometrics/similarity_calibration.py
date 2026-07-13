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


def pairwise_reference_distance_distribution(
    aligned_shapes: np.ndarray,
    *,
    max_pairs: int = 200_000,
) -> np.ndarray:
    """Return a reproducible calibration distribution of reference distances.

    Small reference sets use the exact upper-triangle pairwise distances. Large
    published reference collections would otherwise require billions of
    distances, so they use a deterministic sample of distinct reference pairs.
    """

    shapes = np.asarray(aligned_shapes, dtype=np.float64)
    if shapes.ndim != 3 or shapes.shape[0] < 2 or shapes.shape[1:] != (19, 2):
        raise ValueError("At least two aligned 19-landmark shapes are required.")
    if max_pairs <= 0:
        raise ValueError("max_pairs must be positive.")
    pair_count = shapes.shape[0] * (shapes.shape[0] - 1) // 2
    distances: list[float] = []
    if pair_count <= max_pairs:
        for first in range(shapes.shape[0]):
            for second in range(first + 1, shapes.shape[0]):
                distances.append(float(np.linalg.norm(shapes[first] - shapes[second])))
    else:
        rng = np.random.default_rng(20260713)
        seen_pairs: set[tuple[int, int]] = set()
        while len(distances) < max_pairs:
            first = int(rng.integers(0, shapes.shape[0]))
            second = int(rng.integers(0, shapes.shape[0] - 1))
            if second >= first:
                second += 1
            if first > second:
                first, second = second, first
            pair = (first, second)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            distances.append(float(np.linalg.norm(shapes[first] - shapes[second])))
    return np.asarray(distances, dtype=np.float64)


__all__ = [
    "empirical_similarity_percentile",
    "pairwise_reference_distance_distribution",
]
