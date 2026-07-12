"""Consensus and sample-level shape summaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True, slots=True)
class SampleMeanShapes:
    """Mean aligned configuration for each sample/colony."""

    sample_ids: tuple[str, ...]
    mean_shapes: np.ndarray
    wing_counts: tuple[int, ...]


def mean_shape(shape_stack: np.ndarray) -> np.ndarray:
    """Return a normalized mean shape for already aligned configurations."""

    mean = np.asarray(shape_stack, dtype=np.float64).mean(axis=0)
    centered = mean - mean.mean(axis=0)
    size = float(np.sqrt(np.sum(centered * centered)))
    if size <= 0:
        raise ValueError("Mean shape centroid size must be positive.")
    return centered / size


def sample_mean_shapes(
    aligned_shapes: np.ndarray,
    sample_ids: Iterable[str],
) -> SampleMeanShapes:
    """Group wings by sample/colony and calculate one mean shape per sample."""

    grouped: dict[str, list[np.ndarray]] = defaultdict(list)
    for sample_id, shape in zip(sample_ids, aligned_shapes, strict=True):
        grouped[str(sample_id)].append(np.asarray(shape, dtype=np.float64))
    ordered_sample_ids = tuple(sorted(grouped))
    means = np.asarray([mean_shape(np.asarray(grouped[item])) for item in ordered_sample_ids])
    counts = tuple(len(grouped[item]) for item in ordered_sample_ids)
    return SampleMeanShapes(
        sample_ids=ordered_sample_ids,
        mean_shapes=means,
        wing_counts=counts,
    )


def flatten_shapes(shapes: np.ndarray) -> np.ndarray:
    """Flatten ``(n, 19, 2)`` shapes to ``(n, 38)`` feature rows."""

    array = np.asarray(shapes, dtype=np.float64)
    if array.ndim != 3 or array.shape[1:] != (19, 2):
        raise ValueError("Expected shape stack with dimensions (n, 19, 2).")
    return array.reshape(array.shape[0], 38)


__all__ = ["SampleMeanShapes", "flatten_shapes", "mean_shape", "sample_mean_shapes"]
