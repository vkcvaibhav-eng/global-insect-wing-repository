"""Small deterministic PCA wrapper based on NumPy SVD."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PCAModel:
    """A fitted PCA projection that can be stored in model artifacts."""

    mean: np.ndarray
    components: np.ndarray
    explained_variance: np.ndarray
    retained_component_count: int


def fit_pca(
    features: np.ndarray,
    *,
    variance_threshold: float = 0.99,
    max_components: int | None = None,
) -> PCAModel:
    """Fit PCA by SVD with deterministic component signs."""

    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 1:
        raise ValueError("PCA expects a non-empty 2D feature matrix.")
    mean = matrix.mean(axis=0)
    centered = matrix - mean
    _u_matrix, singular_values, vt_matrix = np.linalg.svd(centered, full_matrices=False)
    components = vt_matrix
    for index, component in enumerate(components):
        pivot = int(np.argmax(np.abs(component)))
        if component[pivot] < 0:
            components[index] *= -1
    denom = max(matrix.shape[0] - 1, 1)
    explained = (singular_values * singular_values) / denom
    if explained.sum() > 0:
        cumulative = np.cumsum(explained / explained.sum())
        retained = int(np.searchsorted(cumulative, variance_threshold) + 1)
    else:
        retained = 1
    if max_components is not None:
        retained = min(retained, max_components)
    retained = max(1, min(retained, components.shape[0]))
    return PCAModel(
        mean=mean,
        components=components[:retained],
        explained_variance=explained[:retained],
        retained_component_count=retained,
    )


def transform_pca(model: PCAModel, features: np.ndarray) -> np.ndarray:
    """Project rows using a saved PCA model; never refit."""

    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    return (matrix - model.mean) @ model.components.T


__all__ = ["PCAModel", "fit_pca", "transform_pca"]
