"""Deterministic linear-discriminant/CVA-style classification."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class LDAClassifier:
    """Parameters for a multiclass linear discriminant classifier."""

    classes: tuple[str, ...]
    class_means: np.ndarray
    covariance_inverse: np.ndarray
    priors: np.ndarray
    sample_counts: dict[str, int]
    regularization: float


def fit_lda(
    features: np.ndarray,
    labels: list[str] | tuple[str, ...],
    *,
    regularization: float = 1e-6,
) -> LDAClassifier:
    """Fit a pooled-covariance classifier with deterministic class order."""

    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=object)
    if x.ndim != 2 or x.shape[0] != y.shape[0] or x.shape[0] == 0:
        raise ValueError("LDA requires one label for every feature row.")
    classes = tuple(sorted(str(item) for item in set(y)))
    if len(classes) < 2:
        raise ValueError("At least two classes are required.")
    means: list[np.ndarray] = []
    counts: dict[str, int] = {}
    pooled = np.zeros((x.shape[1], x.shape[1]), dtype=np.float64)
    pooled_dof = 0
    for class_name in classes:
        rows = x[y == class_name]
        if rows.size == 0:
            continue
        counts[class_name] = int(rows.shape[0])
        mean = rows.mean(axis=0)
        means.append(mean)
        centered = rows - mean
        pooled += centered.T @ centered
        pooled_dof += max(rows.shape[0] - 1, 0)
    covariance = pooled / max(pooled_dof, 1)
    covariance += np.eye(covariance.shape[0]) * regularization
    priors = np.asarray([counts[item] / x.shape[0] for item in classes], dtype=np.float64)
    return LDAClassifier(
        classes=classes,
        class_means=np.asarray(means),
        covariance_inverse=np.linalg.pinv(covariance),
        priors=priors,
        sample_counts=counts,
        regularization=regularization,
    )


def predict_log_probabilities(model: LDAClassifier, features: np.ndarray) -> np.ndarray:
    """Return unnormalized LDA log scores for each class."""

    x = np.asarray(features, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    scores = []
    for class_mean, prior in zip(model.class_means, model.priors, strict=True):
        linear = x @ model.covariance_inverse @ class_mean
        offset = -0.5 * class_mean @ model.covariance_inverse @ class_mean
        scores.append(linear + offset + np.log(max(float(prior), 1e-12)))
    return np.vstack(scores).T


def predict_probabilities(model: LDAClassifier, features: np.ndarray) -> np.ndarray:
    """Return finite class probabilities in saved class order."""

    scores = predict_log_probabilities(model, features)
    scores = scores - scores.max(axis=1, keepdims=True)
    exp_scores = np.exp(scores)
    probabilities = exp_scores / exp_scores.sum(axis=1, keepdims=True)
    return probabilities


def leave_one_sample_out_accuracy(
    features: np.ndarray,
    labels: list[str] | tuple[str, ...],
    sample_ids: list[str] | tuple[str, ...],
) -> dict[str, object]:
    """Cross-validate without splitting a sample/colony across train/test."""

    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=object)
    samples = np.asarray(sample_ids, dtype=object)
    predictions: list[tuple[str, str]] = []
    skipped = 0
    for sample in sorted(set(samples)):
        train = samples != sample
        test = samples == sample
        if len(set(y[train])) < 2:
            skipped += int(test.sum())
            continue
        model = fit_lda(x[train], [str(item) for item in y[train]])
        probs = predict_probabilities(model, x[test])
        for truth, row in zip(y[test], probs, strict=True):
            predictions.append((str(truth), model.classes[int(np.argmax(row))]))
    correct = sum(1 for truth, predicted in predictions if truth == predicted)
    total = len(predictions)
    classes = sorted(set(str(item) for item in y))
    confusion = {
        truth: {predicted: 0 for predicted in classes}
        for truth in classes
    }
    for truth, predicted in predictions:
        confusion[truth][predicted] += 1
    return {
        "total_predictions": total,
        "skipped_predictions": skipped,
        "overall_accuracy": correct / total if total else None,
        "confusion_matrix": confusion,
        "group_leakage_prevented": True,
    }


__all__ = [
    "LDAClassifier",
    "fit_lda",
    "leave_one_sample_out_accuracy",
    "predict_log_probabilities",
    "predict_probabilities",
]
