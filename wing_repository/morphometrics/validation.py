"""Coordinate and result validation for the Apis 19-landmark analysis."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Literal

import numpy as np

from wing_repository.errors import ValidationError
from wing_repository.morphometrics import APIS_STANDARD_LANDMARK_COUNT

ReflectionPolicy = Literal["preserve", "allow"]


@dataclass(frozen=True, slots=True)
class CoordinateValidationResult:
    """Outcome of a 19-landmark coordinate validation."""

    coordinate_count: int
    landmark_order: tuple[int, ...]


def as_coordinate_array(
    coordinates: Iterable[Iterable[float]],
    *,
    expected_count: int = APIS_STANDARD_LANDMARK_COUNT,
) -> np.ndarray:
    """Return a finite ``(expected_count, 2)`` float array.

    The row order is the landmark order.  The function intentionally does not
    sort or relabel rows; preserving source order is part of reproducibility.
    """

    array = np.asarray(list(coordinates), dtype=np.float64)
    if array.shape != (expected_count, 2):
        raise ValidationError(
            f"Expected exactly {expected_count} ordered x,y landmark pairs; "
            f"received shape {array.shape}."
        )
    if not np.all(np.isfinite(array)):
        raise ValidationError("Landmark coordinates must all be finite numbers.")
    return array


def validate_landmark_configuration(
    coordinates: Iterable[Iterable[float]],
    *,
    expected_count: int = APIS_STANDARD_LANDMARK_COUNT,
) -> CoordinateValidationResult:
    """Validate one ordered landmark configuration without changing it."""

    as_coordinate_array(coordinates, expected_count=expected_count)
    return CoordinateValidationResult(
        coordinate_count=expected_count,
        landmark_order=tuple(range(1, expected_count + 1)),
    )


def validate_probabilities(values: Iterable[float], *, tolerance: float = 1e-6) -> None:
    """Require finite probabilities in ``[0, 1]`` that sum to one."""

    probabilities = np.asarray(list(values), dtype=np.float64)
    if probabilities.ndim != 1 or probabilities.size == 0:
        raise ValidationError("At least one probability is required.")
    if not np.all(np.isfinite(probabilities)):
        raise ValidationError("Probabilities must be finite.")
    if np.any(probabilities < -tolerance) or np.any(probabilities > 1 + tolerance):
        raise ValidationError("Probabilities must be between 0 and 1.")
    if not math.isclose(float(probabilities.sum()), 1.0, abs_tol=tolerance):
        raise ValidationError("Probabilities must sum to 1.")


def assert_reflection_policy(policy: ReflectionPolicy) -> ReflectionPolicy:
    """Validate the explicit orientation/reflection policy."""

    if policy not in {"preserve", "allow"}:
        raise ValidationError("Reflection policy must be either 'preserve' or 'allow'.")
    return policy


__all__ = [
    "CoordinateValidationResult",
    "ReflectionPolicy",
    "as_coordinate_array",
    "assert_reflection_policy",
    "validate_landmark_configuration",
    "validate_probabilities",
]
