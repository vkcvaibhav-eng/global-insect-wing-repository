"""Application services for published Apis reference analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.config import get_settings
from wing_repository.enums import (
    AnalysisModelStatus,
    AnalysisOutlierStatus,
    AnalysisQualityStatus,
    AnalysisRunStatus,
    AnalysisType,
    AnnotationStatus,
    Role,
    TemplateStatus,
    WingSide,
    WingType,
)
from wing_repository.errors import AuthorizationError, InvalidStateError, NotFoundError, ValidationError
from wing_repository.models import (
    AnalysisModel,
    Annotation,
    ExternalReferenceShape,
    LandmarkTemplate,
    LineageProbability,
    PublishedShapeMatch,
    RegionProbability,
    User,
    WingAnalysisRun,
)
from wing_repository.morphometrics.artifacts import load_pickle_artifact, save_pickle_artifact
from wing_repository.morphometrics.classification import ranked_probability_results
from wing_repository.morphometrics.consensus import flatten_shapes, sample_mean_shapes
from wing_repository.morphometrics.cva import (
    LDAClassifier,
    fit_lda,
    leave_one_sample_out_accuracy,
    predict_probabilities,
)
from wing_repository.morphometrics.gpa import align_query_to_consensus, generalized_procrustes
from wing_repository.morphometrics.nearest_shapes import nearest_shapes
from wing_repository.morphometrics.outlier_detection import detect_outlier
from wing_repository.morphometrics.pca import PCAModel, fit_pca, transform_pca
from wing_repository.morphometrics.provenance import software_versions
from wing_repository.morphometrics.similarity_calibration import (
    empirical_similarity_percentile,
    pairwise_reference_distance_distribution,
)
from wing_repository.morphometrics.validation import as_coordinate_array, validate_probabilities
from wing_repository.services import require_active_role, validate_annotation_complete

APIS_STANDARD_TEMPLATE_NAME = "Apis right forewing standard 19-landmark template"
OLEKSA_CITATION = (
    "Oleksa, A. et al. (2023). Honey bee (Apis mellifera) wing images: "
    "a tool for identification and conservation. GigaScience 12: giad019. "
    "Article DOI: 10.1093/gigascience/giad019; Dataset DOI: 10.5281/zenodo.7244070."
)
NAWROCKA_CITATION = (
    "Nawrocka, A., Kandemir, I., Fuchs, S. and Tofilski, A. (2018). "
    "Dataset DOI: 10.5281/zenodo.7567336."
)
WORKFLOW_CITATION = "Workflow DOI: 10.48546/workflowhub.workflow.422.1."
SINGLE_WING_WARNING = (
    "Results from a single wing are less reliable than results based on the "
    "mean shape of multiple workers from one colony or locality."
)
NO_REGION_MATCH_WARNING = (
    "No reliable geographical reference match within the current European "
    "reference dataset."
)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def annotation_shape_matrix(annotation: Annotation) -> np.ndarray:
    """Return query coordinates in template ordinal order."""

    validate_annotation_complete(annotation)
    points = sorted(annotation.points, key=lambda point: point.template_landmark.ordinal)
    coordinates = [(point.x_pixel, point.y_pixel) for point in points]
    return as_coordinate_array(coordinates)


def require_published_apis_query(actor: User, annotation: Annotation, model: AnalysisModel) -> None:
    """Validate role, ownership, template, taxon and wing scope."""

    require_active_role(actor, Role.STUDENT, Role.EXPERT_REVIEWER, Role.ADMINISTRATOR)
    if actor.role is Role.STUDENT and annotation.contributor_id != actor.id:
        raise AuthorizationError("Students can analyse only their own annotations.")
    if annotation.template_id != model.template_id:
        raise InvalidStateError(
            "Published Apis analysis requires the exact active 19-landmark template."
        )
    if len(annotation.template.landmarks) != 19:
        raise InvalidStateError("Published Apis analysis requires exactly 19 landmarks.")
    if annotation.template.status is not TemplateStatus.PUBLISHED:
        raise InvalidStateError(
            "The 19-landmark analysis template must be approved/published before use."
        )
    if annotation.template.taxon.genus != "Apis":
        raise InvalidStateError("Published Apis analysis is restricted to genus Apis.")
    species_text = (annotation.wing_image.specimen.species_text or "").casefold()
    if species_text and "mellifera" not in species_text:
        raise InvalidStateError("This module is restricted to Apis mellifera.")
    if (
        annotation.template.side is not WingSide.RIGHT
        or annotation.template.wing_type is not WingType.FOREWING
        or annotation.wing_image.side is not WingSide.RIGHT
        or annotation.wing_image.wing_type is not WingType.FOREWING
    ):
        raise InvalidStateError("Only right forewings are supported.")
    if annotation.status not in {
        AnnotationStatus.DRAFT,
        AnnotationStatus.SUBMITTED,
        AnnotationStatus.RETURNED,
        AnnotationStatus.APPROVED,
    }:
        raise InvalidStateError("The annotation is not available for analysis.")
    annotation_shape_matrix(annotation)


def active_analysis_model(session: Session, analysis_type: AnalysisType) -> AnalysisModel:
    """Return the sole active model for an analysis type."""

    models = list(
        session.scalars(
            select(AnalysisModel)
            .where(
                AnalysisModel.analysis_type == analysis_type,
                AnalysisModel.model_status == AnalysisModelStatus.ACTIVE,
            )
            .order_by(AnalysisModel.activated_at.desc(), AnalysisModel.id.desc())
        )
    )
    if not models:
        raise NotFoundError(f"No active model is available for {analysis_type.value}.")
    return models[0]


def _load_model_payload(model: AnalysisModel) -> dict[str, Any]:
    if model.artifact_storage_key is None or model.artifact_sha256 is None:
        raise InvalidStateError("The active analysis model has no artifact.")
    return load_pickle_artifact(
        root=get_settings().analysis_artifact_dir,
        storage_key=model.artifact_storage_key,
        expected_sha256=model.artifact_sha256,
    )


def _one_label_per_sample(
    sample_ids: Iterable[str],
    labels: Iterable[str | None],
) -> dict[str, str]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for sample_id, label in zip(sample_ids, labels, strict=True):
        if label:
            grouped[str(sample_id)].append(str(label))
    result: dict[str, str] = {}
    for sample_id, values in grouped.items():
        [(label, _count)] = Counter(values).most_common(1)
        result[sample_id] = label
    return result


def build_reference_payload(
    *,
    coordinates: np.ndarray,
    external_shape_ids: list[int],
    sample_ids: list[str],
    region_labels: list[str | None],
    lineage_labels: list[str | None],
    source_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic reference artifact from imported 19-point shapes."""

    shapes = np.asarray(coordinates, dtype=np.float64)
    if shapes.ndim != 3 or shapes.shape[1:] != (19, 2):
        raise ValidationError("Reference coordinates must have shape (n, 19, 2).")
    if not (len(external_shape_ids) == len(sample_ids) == len(region_labels) == len(lineage_labels) == shapes.shape[0]):
        raise ValidationError("Reference metadata must align one-to-one with coordinates.")
    gpa_result = generalized_procrustes(shapes, reflection_policy="preserve")
    means = sample_mean_shapes(gpa_result.aligned_shapes, sample_ids)
    region_by_sample = _one_label_per_sample(sample_ids, region_labels)
    lineage_by_sample = _one_label_per_sample(sample_ids, lineage_labels)
    region_rows = [
        index for index, sample_id in enumerate(means.sample_ids) if sample_id in region_by_sample
    ]
    lineage_rows = [
        index for index, sample_id in enumerate(means.sample_ids) if sample_id in lineage_by_sample
    ]
    if len(region_rows) < 2 or len(lineage_rows) < 4:
        raise ValidationError("Insufficient labelled sample means for region/lineage models.")
    region_sample_labels = [region_by_sample[means.sample_ids[index]] for index in region_rows]
    lineage_sample_labels = [
        lineage_by_sample[means.sample_ids[index]] for index in lineage_rows
    ]
    if len(set(region_sample_labels)) < 2:
        raise ValidationError("At least two regional reference groups are required.")
    if set(lineage_sample_labels) != {"A", "C", "M", "O"}:
        raise ValidationError("Lineage reference data must include A, C, M and O.")
    model_sample_ids = list(means.sample_ids)
    features = flatten_shapes(means.mean_shapes)
    pca_model = fit_pca(features, max_components=min(10, max(1, len(model_sample_ids) - 1)))
    scores = transform_pca(pca_model, features)
    region_classifier = fit_lda(scores[region_rows], region_sample_labels)
    lineage_classifier = fit_lda(scores[lineage_rows], lineage_sample_labels)
    distance_distribution = pairwise_reference_distance_distribution(gpa_result.aligned_shapes)
    validation_metrics = {
        "gpa_converged": gpa_result.converged,
        "gpa_iterations": gpa_result.iterations,
        "reflection_policy": gpa_result.reflection_policy,
        "region_leave_one_sample_out": leave_one_sample_out_accuracy(
            scores[region_rows],
            region_sample_labels,
            [means.sample_ids[index] for index in region_rows],
        ),
        "lineage_leave_one_sample_out": leave_one_sample_out_accuracy(
            scores[lineage_rows],
            lineage_sample_labels,
            [means.sample_ids[index] for index in lineage_rows],
        ),
        "outlier_distance_quantile": 0.99,
        "single_wing_warning": SINGLE_WING_WARNING,
    }
    return {
        "artifact_schema_version": "1.0",
        "taxon": "Apis mellifera",
        "wing": "right forewing",
        "landmark_count": 19,
        "consensus": gpa_result.consensus,
        "aligned_reference_shapes": gpa_result.aligned_shapes,
        "external_shape_ids": list(external_shape_ids),
        "sample_ids": list(sample_ids),
        "sample_mean_shapes": means.mean_shapes,
        "model_sample_ids": model_sample_ids,
        "pca_model": pca_model,
        "region_classifier": region_classifier,
        "lineage_classifier": lineage_classifier,
        "distance_distribution": distance_distribution,
        "validation_metrics": validation_metrics,
        "software_versions": software_versions(),
        "source_hashes": source_hashes or {},
        "preprocessing": {
            "orientation": "source orientation preserved; no reflection applied",
            "gpa": "centered, unit centroid size, rotate only",
            "size": "centroid size retained only as source-coordinate analytical value",
        },
    }


def save_reference_payload_models(
    session: Session,
    *,
    template_id: int,
    payload: dict[str, Any],
    artifact_root: Path,
    model_version: int,
    source_dataset_ids: list[int],
) -> list[AnalysisModel]:
    """Persist one artifact and three validated model records."""

    storage_key = f"apis_reference/v{model_version}/model.pkl"
    stored = save_pickle_artifact(payload, root=artifact_root, storage_key=storage_key)
    validation_metrics = payload.get("validation_metrics", {})
    source_hashes = payload.get("source_hashes", {})
    preprocessing = payload.get("preprocessing", {})
    software = payload.get("software_versions", {})
    model_rows = [
        ("APIS_MELLIFERA_EU_REGION", AnalysisType.APIS_MELLIFERA_EU_REGION),
        ("APIS_MELLIFERA_LINEAGE", AnalysisType.APIS_MELLIFERA_LINEAGE),
        ("APIS_MELLIFERA_NEAREST_SHAPE", AnalysisType.APIS_MELLIFERA_NEAREST_SHAPE),
    ]
    models: list[AnalysisModel] = []
    for model_code, analysis_type in model_rows:
        model = AnalysisModel(
            model_code=model_code,
            model_version=model_version,
            template_id=template_id,
            analysis_type=analysis_type,
            source_dataset_ids=_json_dumps(source_dataset_ids),
            reference_wing_count=int(len(payload["external_shape_ids"])),
            reference_sample_count=int(len(payload["model_sample_ids"])),
            preprocessing_json=_json_dumps(preprocessing),
            software_versions_json=_json_dumps(software),
            source_hashes_json=_json_dumps(source_hashes),
            validation_metrics_json=_json_dumps(validation_metrics),
            artifact_storage_key=stored.storage_key,
            artifact_sha256=stored.sha256,
            model_status=AnalysisModelStatus.VALIDATED,
        )
        session.add(model)
        models.append(model)
    session.commit()
    return models


def activate_validated_models(
    session: Session,
    *,
    model_version: int,
    template_id: int,
) -> list[AnalysisModel]:
    """Activate a validated model version and retire older active versions."""

    template = session.get(LandmarkTemplate, template_id)
    if template is None or template.status is not TemplateStatus.PUBLISHED:
        raise InvalidStateError(
            "The Apis 19-landmark template must be published before model activation."
        )
    selected = list(
        session.scalars(
            select(AnalysisModel).where(
                AnalysisModel.template_id == template_id,
                AnalysisModel.model_version == model_version,
                AnalysisModel.model_status == AnalysisModelStatus.VALIDATED,
            )
        )
    )
    if {model.analysis_type for model in selected} != set(AnalysisType):
        raise InvalidStateError("A complete validated region/lineage/nearest model set is required.")
    for active in session.scalars(
        select(AnalysisModel).where(
            AnalysisModel.template_id == template_id,
            AnalysisModel.model_status == AnalysisModelStatus.ACTIVE,
        )
    ):
        active.model_status = AnalysisModelStatus.RETIRED
    now = _utc_now()
    for model in selected:
        model.model_status = AnalysisModelStatus.ACTIVE
        model.activated_at = now
    session.commit()
    return selected


def run_published_apis_reference_analysis(
    session: Session,
    actor: User,
    *,
    annotation_id: int,
    nearest_limit: int = 10,
) -> WingAnalysisRun:
    """Run preliminary single-wing Apis reference analysis and persist results."""

    nearest_model = active_analysis_model(
        session,
        AnalysisType.APIS_MELLIFERA_NEAREST_SHAPE,
    )
    region_model = active_analysis_model(session, AnalysisType.APIS_MELLIFERA_EU_REGION)
    lineage_model = active_analysis_model(session, AnalysisType.APIS_MELLIFERA_LINEAGE)
    annotation = session.get(Annotation, annotation_id)
    if annotation is None:
        raise NotFoundError("Annotation was not found.")
    require_published_apis_query(actor, annotation, nearest_model)
    if (
        region_model.template_id != nearest_model.template_id
        or lineage_model.template_id != nearest_model.template_id
    ):
        raise InvalidStateError("Active analysis models do not share one exact template.")

    nearest_payload = _load_model_payload(nearest_model)
    region_payload = _load_model_payload(region_model)
    lineage_payload = _load_model_payload(lineage_model)
    query_shape = annotation_shape_matrix(annotation)
    query_aligned = align_query_to_consensus(query_shape, nearest_payload["consensus"])
    region_scores = transform_pca(
        region_payload["pca_model"],
        flatten_shapes(query_aligned.reshape(1, 19, 2)),
    )
    lineage_scores = transform_pca(
        lineage_payload["pca_model"],
        flatten_shapes(query_aligned.reshape(1, 19, 2)),
    )
    region_classifier: LDAClassifier = region_payload["region_classifier"]
    lineage_classifier: LDAClassifier = lineage_payload["lineage_classifier"]
    region_probabilities = predict_probabilities(region_classifier, region_scores)[0]
    lineage_probabilities = predict_probabilities(lineage_classifier, lineage_scores)[0]
    validate_probabilities(region_probabilities, tolerance=1e-5)
    validate_probabilities(lineage_probabilities, tolerance=1e-5)
    if set(lineage_classifier.classes) != {"A", "C", "M", "O"}:
        raise InvalidStateError("The active lineage model must contain A, C, M and O.")

    nearest = nearest_shapes(
        query_aligned,
        nearest_payload["aligned_reference_shapes"],
        nearest_payload["external_shape_ids"],
        limit=nearest_limit,
    )
    if not nearest:
        raise InvalidStateError("The active nearest-shape model has no references.")
    distance_distribution = nearest_payload["distance_distribution"]
    outlier = detect_outlier(nearest[0].procrustes_distance, distance_distribution)
    warning_parts = [SINGLE_WING_WARNING]
    outlier_status = AnalysisOutlierStatus.IN_DISTRIBUTION
    quality_status = AnalysisQualityStatus.PASS
    if outlier.is_outlier:
        outlier_status = AnalysisOutlierStatus.OUTSIDE_REFERENCE_DISTRIBUTION
        quality_status = AnalysisQualityStatus.WARNING
        warning_parts.append(NO_REGION_MATCH_WARNING)
    warning_parts.append(
        f"Model versions: region v{region_model.model_version}, "
        f"lineage v{lineage_model.model_version}, nearest v{nearest_model.model_version}."
    )
    run = WingAnalysisRun(
        query_annotation_id=annotation.id,
        model_id=nearest_model.id,
        status=AnalysisRunStatus.COMPLETED,
        preliminary_single_wing=True,
        quality_status=quality_status,
        outlier_status=outlier_status,
        warning_text=" ".join(warning_parts),
        completed_at=_utc_now(),
    )
    session.add(run)
    session.flush()
    for result in ranked_probability_results(
        region_classifier.classes,
        region_probabilities,
        region_classifier.sample_counts,
        outlier=outlier.is_outlier,
    ):
        session.add(
            RegionProbability(
                analysis_run_id=run.id,
                rank=result.rank,
                reference_group=result.label,
                probability=result.probability,
                reference_sample_count=result.reference_sample_count,
                interpretation=result.interpretation,
            )
        )
    lineage_results = ranked_probability_results(
        lineage_classifier.classes,
        lineage_probabilities,
        lineage_classifier.sample_counts,
        outlier=outlier.is_outlier,
    )
    for result in lineage_results:
        session.add(
            LineageProbability(
                analysis_run_id=run.id,
                rank=result.rank,
                lineage_code=result.label,
                probability=result.probability,
                reference_sample_count=result.reference_sample_count,
                interpretation=result.interpretation,
            )
        )
    for match in nearest:
        session.add(
            PublishedShapeMatch(
                analysis_run_id=run.id,
                rank=match.rank,
                external_reference_shape_id=match.external_reference_shape_id,
                procrustes_distance=match.procrustes_distance,
                similarity_percentile=empirical_similarity_percentile(
                    match.procrustes_distance,
                    distance_distribution,
                ),
            )
        )
    session.commit()
    return run


def active_query_annotations(session: Session, actor: User) -> list[Annotation]:
    """Return complete 19-landmark annotations available to a user."""

    require_active_role(actor, Role.STUDENT, Role.EXPERT_REVIEWER, Role.ADMINISTRATOR)
    statement = (
        select(Annotation)
        .join(Annotation.template)
        .where(Annotation.status.in_([AnnotationStatus.DRAFT, AnnotationStatus.SUBMITTED, AnnotationStatus.APPROVED]))
        .order_by(Annotation.created_at.desc())
    )
    if actor.role is Role.STUDENT:
        statement = statement.where(Annotation.contributor_id == actor.id)
    candidates = list(session.scalars(statement))
    return [
        annotation
        for annotation in candidates
        if len(annotation.template.landmarks) == 19
        and len(annotation.points) == 19
        and annotation.template.taxon.genus == "Apis"
    ]


def published_shape_match_rows(run: WingAnalysisRun) -> list[dict[str, Any]]:
    """Return UI rows for nearest external matches."""

    return [
        {
            "Rank": match.rank,
            "Source taxon": match.external_reference_shape.taxon_name,
            "Published source record": match.external_reference_shape.source_record_identifier,
            "Source sample": match.external_reference_shape.source_sample_identifier,
            "Country": match.external_reference_shape.country_code,
            "Procrustes distance": match.procrustes_distance,
            "Similarity percentile": match.similarity_percentile,
            "Reference label": "External published reference",
        }
        for match in sorted(run.published_shape_matches, key=lambda item: item.rank)
    ]


__all__ = [
    "NAWROCKA_CITATION",
    "NO_REGION_MATCH_WARNING",
    "OLEKSA_CITATION",
    "SINGLE_WING_WARNING",
    "WORKFLOW_CITATION",
    "activate_validated_models",
    "active_analysis_model",
    "active_query_annotations",
    "annotation_shape_matrix",
    "build_reference_payload",
    "published_shape_match_rows",
    "require_published_apis_query",
    "run_published_apis_reference_analysis",
    "save_reference_payload_models",
]
