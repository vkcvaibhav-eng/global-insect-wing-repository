"""Ordinary Procrustes alignment for two landmark configurations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wing_repository.morphometrics.validation import (
    ReflectionPolicy,
    as_coordinate_array,
    assert_reflection_policy,
)


@dataclass(frozen=True, slots=True)
class OrdinaryProcrustesResult:
    """A shape aligned to a fixed reference plus the rotation matrix used."""

    aligned: np.ndarray
    reference: np.ndarray
    rotation: np.ndarray
    distance: float
    reflected: bool


def centroid_size(shape: np.ndarray) -> float:
    """Return centroid size in source-coordinate units."""

    centered = shape - shape.mean(axis=0)
    return float(np.sqrt(np.sum(centered * centered)))


def center_and_scale(coordinates: np.ndarray) -> np.ndarray:
    """Center a configuration and scale it to unit centroid size."""

    shape = as_coordinate_array(coordinates)
    centered = shape - shape.mean(axis=0)
    size = centroid_size(shape)
    if size <= 0:
        raise ValueError("Centroid size must be positive.")
    return centered / size


def align_to_reference(
    coordinates: np.ndarray,
    reference: np.ndarray,
    *,
    reflection_policy: ReflectionPolicy = "preserve",
) -> OrdinaryProcrustesResult:
    """Align one centered/scaled shape to a centered/scaled reference.

    ``reflection_policy='preserve'`` forbids mirror flipping.  This is the safe
    default for right-forewing analysis until a published workflow transformation
    is explicitly documented.
    """

    policy = assert_reflection_policy(reflection_policy)
    shape = center_and_scale(coordinates)
    target = center_and_scale(reference)
    u_matrix, _singular_values, vt_matrix = np.linalg.svd(shape.T @ target)
    rotation = u_matrix @ vt_matrix
    reflected = bool(np.linalg.det(rotation) < 0)
    if reflected and policy == "preserve":
        u_matrix[:, -1] *= -1
        rotation = u_matrix @ vt_matrix
        reflected = False
    aligned = shape @ rotation
    return OrdinaryProcrustesResult(
        aligned=aligned,
        reference=target,
        rotation=rotation,
        distance=float(np.linalg.norm(aligned - target)),
        reflected=reflected,
    )


def procrustes_distance(
    coordinates: np.ndarray,
    reference: np.ndarray,
    *,
    reflection_policy: ReflectionPolicy = "preserve",
) -> float:
    """Return ordinary Procrustes distance between two configurations."""

    return align_to_reference(
        coordinates,
        reference,
        reflection_policy=reflection_policy,
    ).distance


__all__ = [
    "OrdinaryProcrustesResult",
    "align_to_reference",
    "center_and_scale",
    "centroid_size",
    "procrustes_distance",
]
