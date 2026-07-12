"""Generalized Procrustes Analysis for 2D landmark configurations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wing_repository.morphometrics.ordinary_procrustes import (
    align_to_reference,
    center_and_scale,
    centroid_size,
)
from wing_repository.morphometrics.validation import ReflectionPolicy, as_coordinate_array


@dataclass(frozen=True, slots=True)
class GPAResult:
    """Aligned shapes and their consensus after Generalized Procrustes Analysis."""

    aligned_shapes: np.ndarray
    consensus: np.ndarray
    centroid_sizes: np.ndarray
    iterations: int
    converged: bool
    reflection_policy: ReflectionPolicy


def _normalize_consensus(consensus: np.ndarray) -> np.ndarray:
    centered = consensus - consensus.mean(axis=0)
    size = float(np.sqrt(np.sum(centered * centered)))
    if size <= 0:
        raise ValueError("Consensus centroid size must be positive.")
    return centered / size


def generalized_procrustes(
    shapes: np.ndarray,
    *,
    reflection_policy: ReflectionPolicy = "preserve",
    tolerance: float = 1e-10,
    max_iterations: int = 100,
) -> GPAResult:
    """Perform deterministic GPA without allowing reflection by default."""

    array = np.asarray(shapes, dtype=np.float64)
    if array.ndim != 3 or array.shape[1:] != (19, 2):
        raise ValueError("GPA expects an array of shape (n, 19, 2).")
    if array.shape[0] < 1:
        raise ValueError("At least one shape is required for GPA.")
    for shape in array:
        as_coordinate_array(shape)

    centroid_sizes = np.asarray([centroid_size(shape) for shape in array])
    aligned = np.asarray([center_and_scale(shape) for shape in array])
    consensus = _normalize_consensus(aligned.mean(axis=0))
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        aligned = np.asarray(
            [
                align_to_reference(
                    shape,
                    consensus,
                    reflection_policy=reflection_policy,
                ).aligned
                for shape in array
            ]
        )
        next_consensus = _normalize_consensus(aligned.mean(axis=0))
        delta = float(np.linalg.norm(next_consensus - consensus))
        consensus = next_consensus
        if delta <= tolerance:
            converged = True
            break
    return GPAResult(
        aligned_shapes=aligned,
        consensus=consensus,
        centroid_sizes=centroid_sizes,
        iterations=iterations,
        converged=converged,
        reflection_policy=reflection_policy,
    )


def align_query_to_consensus(
    coordinates: np.ndarray,
    consensus: np.ndarray,
    *,
    reflection_policy: ReflectionPolicy = "preserve",
) -> np.ndarray:
    """Align a query to a saved consensus without rebuilding GPA."""

    return align_to_reference(
        coordinates,
        consensus,
        reflection_policy=reflection_policy,
    ).aligned


__all__ = ["GPAResult", "align_query_to_consensus", "generalized_procrustes"]
