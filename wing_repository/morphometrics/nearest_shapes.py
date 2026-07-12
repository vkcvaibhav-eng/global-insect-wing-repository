"""Nearest published shape search using saved aligned reference shapes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class NearestShape:
    """One nearest-neighbour match in Procrustes shape space."""

    rank: int
    external_reference_shape_id: int
    procrustes_distance: float


def procrustes_distances(query_aligned: np.ndarray, reference_aligned: np.ndarray) -> np.ndarray:
    """Calculate distances from one aligned query to aligned references."""

    query = np.asarray(query_aligned, dtype=np.float64)
    references = np.asarray(reference_aligned, dtype=np.float64)
    if query.shape != (19, 2) or references.ndim != 3 or references.shape[1:] != (19, 2):
        raise ValueError("Expected query (19, 2) and references (n, 19, 2).")
    return np.sqrt(np.sum((references - query) ** 2, axis=(1, 2)))


def nearest_shapes(
    query_aligned: np.ndarray,
    reference_aligned: np.ndarray,
    reference_shape_ids: list[int] | tuple[int, ...],
    *,
    limit: int = 10,
) -> list[NearestShape]:
    """Return nearest published coordinate configurations."""

    distances = procrustes_distances(query_aligned, reference_aligned)
    if len(reference_shape_ids) != distances.size:
        raise ValueError("Reference IDs must align with reference shape rows.")
    order = np.argsort(distances, kind="mergesort")[:limit]
    return [
        NearestShape(
            rank=index + 1,
            external_reference_shape_id=int(reference_shape_ids[position]),
            procrustes_distance=float(distances[position]),
        )
        for index, position in enumerate(order)
    ]


__all__ = ["NearestShape", "nearest_shapes", "procrustes_distances"]
