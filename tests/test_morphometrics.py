from __future__ import annotations

import math

import numpy as np
import pytest

from wing_repository.errors import ValidationError
from wing_repository.morphometrics.classification import ranked_probability_results
from wing_repository.morphometrics.consensus import flatten_shapes
from wing_repository.morphometrics.cva import (
    fit_lda,
    leave_one_sample_out_accuracy,
    predict_probabilities,
)
from wing_repository.morphometrics.gpa import align_query_to_consensus, generalized_procrustes
from wing_repository.morphometrics.ordinary_procrustes import (
    align_to_reference,
    procrustes_distance,
)
from wing_repository.morphometrics.pca import fit_pca, transform_pca
from wing_repository.morphometrics.similarity_calibration import (
    empirical_similarity_percentile,
)
from wing_repository.morphometrics.validation import (
    as_coordinate_array,
    validate_landmark_configuration,
)


def _base_shape() -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, 19, endpoint=False)
    return np.column_stack((np.cos(angles) + 0.05 * np.arange(19), 0.45 * np.sin(angles)))


def test_exact_19_point_validation_and_rejection() -> None:
    shape = _base_shape()
    result = validate_landmark_configuration(shape)

    assert result.coordinate_count == 19
    assert result.landmark_order == tuple(range(1, 20))
    with pytest.raises(ValidationError):
        as_coordinate_array(shape[:18])
    with pytest.raises(ValidationError):
        as_coordinate_array(np.vstack([shape, shape[0]]))


def test_landmark_order_is_preserved() -> None:
    shape = _base_shape()
    reversed_shape = shape[::-1]

    assert np.array_equal(as_coordinate_array(reversed_shape), reversed_shape)


def test_gpa_translation_rotation_and_scale_invariance() -> None:
    shape = _base_shape()
    theta = math.radians(37)
    rotation = np.asarray(
        [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]]
    )
    transformed = shape @ rotation * 3.7 + np.asarray([42.0, -13.0])
    result = generalized_procrustes(np.asarray([shape, transformed]))

    assert result.converged
    assert np.linalg.norm(result.aligned_shapes[0] - result.aligned_shapes[1]) < 1e-10


def test_reflection_policy_is_explicit_and_preserves_orientation_by_default() -> None:
    shape = _base_shape()
    reflected = shape * np.asarray([-1.0, 1.0])
    preserved = align_to_reference(reflected, shape, reflection_policy="preserve")
    allowed = align_to_reference(reflected, shape, reflection_policy="allow")

    assert not preserved.reflected
    assert allowed.reflected
    assert allowed.distance < preserved.distance


def test_query_projection_uses_saved_pca_without_rebuilding() -> None:
    shapes = np.asarray([_base_shape() + index * 0.01 for index in range(4)])
    gpa = generalized_procrustes(shapes)
    features = flatten_shapes(gpa.aligned_shapes)
    model = fit_pca(features)
    original_mean = model.mean.copy()

    query = align_query_to_consensus(shapes[0] + 100, gpa.consensus)
    scores = transform_pca(model, flatten_shapes(query.reshape(1, 19, 2)))

    assert scores.shape[0] == 1
    assert np.array_equal(model.mean, original_mean)


def test_identical_procrustes_distance_is_zero() -> None:
    shape = _base_shape()

    assert procrustes_distance(shape, shape) == pytest.approx(0.0, abs=1e-12)


def test_lower_distance_has_higher_similarity_percentile() -> None:
    distribution = np.asarray([0.1, 0.2, 0.3, 0.4])

    assert empirical_similarity_percentile(0.1, distribution) > empirical_similarity_percentile(
        0.35,
        distribution,
    )


def test_regional_and_lineage_probabilities_sum_to_one() -> None:
    features = np.asarray(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [2.0, 2.0],
            [2.1, 2.0],
        ]
    )
    classifier = fit_lda(features, ["ES-PT", "ES-PT", "HR-SI", "HR-SI"])
    probabilities = predict_probabilities(classifier, np.asarray([[0.05, 0.0]]))[0]
    rows = ranked_probability_results(
        classifier.classes,
        probabilities,
        classifier.sample_counts,
    )

    assert probabilities.sum() == pytest.approx(1.0)
    assert sum(row.probability for row in rows) == pytest.approx(1.0)


def test_sample_level_grouping_prevents_colony_leakage() -> None:
    features = np.asarray(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [2.0, 2.0],
            [2.1, 2.0],
        ]
    )
    result = leave_one_sample_out_accuracy(
        features,
        ["A", "A", "C", "C"],
        ["colony-1", "colony-1", "colony-2", "colony-2"],
    )

    assert result["group_leakage_prevented"] is True
