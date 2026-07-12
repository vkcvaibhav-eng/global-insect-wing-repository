"""Exact-template, approved-only CSV and TPS export serializers."""

from __future__ import annotations

import csv
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from .enums import AnnotationStatus, ReviewDecision
from .errors import (
    ExportError,
    NotFoundError,
    TemplateVersionMismatchError,
    ValidationError,
)
from .models import (
    Annotation,
    AnnotationPoint,
    LandmarkTemplate,
    RepositoryRecord,
    TemplateLandmark,
)
from .services import validate_annotation_complete

CSV_COLUMNS = (
    "accession_number",
    "order",
    "genus",
    "genus_code",
    "template_id",
    "template_name",
    "template_version",
    "annotation_id",
    "annotation_revision",
    "specimen_code",
    "species",
    "species_identification_method",
    "genbank_accession",
    "taxonomist_name",
    "sex",
    "collection_date",
    "country",
    "locality",
    "locality_sample_code",
    "locality_sample_size",
    "locality_sample_number",
    "collector",
    "original_filename",
    "image_sha256",
    "image_width",
    "image_height",
    "landmark_ordinal",
    "landmark_label",
    "x_pixel",
    "y_pixel",
    "x_normalized",
    "y_normalized",
    "scale_reference_length",
    "scale_reference_unit",
    "scale_reference_pixels",
    "mm_per_pixel",
    "x_mm",
    "y_mm",
)


def approved_records_for_template(
    session: Session,
    *,
    template_id: int,
) -> tuple[LandmarkTemplate, list[RepositoryRecord]]:
    """Return accessioned records for one and only one template identity."""

    template = session.get(LandmarkTemplate, template_id)
    if template is None:
        raise NotFoundError("Landmark template was not found.")
    records = list(
        session.scalars(
            select(RepositoryRecord)
            .join(Annotation, RepositoryRecord.annotation_id == Annotation.id)
            .where(
                Annotation.template_id == template.id,
                Annotation.status == AnnotationStatus.APPROVED,
            )
            .order_by(RepositoryRecord.accession_number.asc())
        )
    )
    for record in records:
        annotation = record.annotation
        if annotation.template_id != template.id:
            raise TemplateVersionMismatchError(
                "Repository query included a different template identity."
            )
        if record.taxon_id != template.taxon_id:
            raise TemplateVersionMismatchError(
                "Repository record genus differs from its landmark template."
            )
        if annotation.status is not AnnotationStatus.APPROVED:
            raise ExportError("An unapproved annotation reached the export set.")
        if (
            record.review.annotation_id != annotation.id
            or record.review.decision is not ReviewDecision.APPROVE
        ):
            raise ExportError("Repository record does not have a matching approval review.")
    return template, records


def _ordered_points(
    annotation: Annotation,
    template: LandmarkTemplate,
) -> list[tuple[TemplateLandmark, AnnotationPoint]]:
    try:
        validate_annotation_complete(annotation)
    except ValidationError as exc:
        raise ExportError(
            f"Approved annotation {annotation.id} has invalid coordinate data."
        ) from exc
    landmarks = sorted(template.landmarks, key=lambda landmark: landmark.ordinal)
    points = {point.template_landmark_id: point for point in annotation.points}
    expected_ids = {landmark.id for landmark in landmarks}
    if not landmarks or set(points) != expected_ids:
        raise ExportError(
            f"Approved annotation {annotation.id} does not contain its exact template point set."
        )
    return [(landmark, points[landmark.id]) for landmark in landmarks]


def export_approved_csv(session: Session, *, template_id: int) -> str:
    """Serialize a long-form coordinate CSV for one exact template version."""

    template, records = approved_records_for_template(session, template_id=template_id)
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        annotation = record.annotation
        image = annotation.wing_image
        specimen = image.specimen
        taxon = record.taxon
        mm_per_pixel = image.scale_mm_per_pixel
        for landmark, point in _ordered_points(annotation, template):
            writer.writerow(
                {
                    "accession_number": record.accession_number,
                    "order": taxon.order_name,
                    "genus": taxon.genus,
                    "genus_code": taxon.genus_code,
                    "template_id": template.id,
                    "template_name": template.name,
                    "template_version": template.version,
                    "annotation_id": annotation.id,
                    "annotation_revision": annotation.revision_number,
                    "specimen_code": specimen.specimen_code,
                    "species": specimen.species_text,
                    "species_identification_method": (
                        specimen.species_identification_method.value
                        if specimen.species_identification_method is not None
                        else None
                    ),
                    "genbank_accession": specimen.genbank_accession,
                    "taxonomist_name": specimen.taxonomist_name,
                    "sex": specimen.sex,
                    "collection_date": specimen.collection_date,
                    "country": specimen.country,
                    "locality": specimen.locality,
                    "locality_sample_code": specimen.locality_sample_code,
                    "locality_sample_size": specimen.locality_sample_size,
                    "locality_sample_number": specimen.locality_sample_number,
                    "collector": specimen.collector_name,
                    "original_filename": image.original_filename,
                    "image_sha256": image.sha256,
                    "image_width": annotation.image_width,
                    "image_height": annotation.image_height,
                    "landmark_ordinal": landmark.ordinal,
                    "landmark_label": landmark.label,
                    "x_pixel": point.x_pixel,
                    "y_pixel": point.y_pixel,
                    "x_normalized": point.x_normalized,
                    "y_normalized": point.y_normalized,
                    "scale_reference_length": image.scale_reference_length,
                    "scale_reference_unit": image.scale_reference_unit,
                    "scale_reference_pixels": image.scale_reference_pixels,
                    "mm_per_pixel": mm_per_pixel,
                    "x_mm": (
                        point.x_pixel * mm_per_pixel
                        if mm_per_pixel is not None
                        else None
                    ),
                    "y_mm": (
                        point.y_pixel * mm_per_pixel
                        if mm_per_pixel is not None
                        else None
                    ),
                }
            )
    return output.getvalue()


def _format_coordinate(value: float) -> str:
    return format(value, ".12g")


def export_approved_tps(session: Session, *, template_id: int) -> str:
    """Serialize raw source-pixel landmarks as TPS for one exact template."""

    template, records = approved_records_for_template(session, template_id=template_id)
    blocks: list[str] = []
    for record in records:
        annotation = record.annotation
        ordered_points = _ordered_points(annotation, template)
        lines = [f"LM={len(ordered_points)}"]
        lines.extend(
            f"{_format_coordinate(point.x_pixel)} {_format_coordinate(point.y_pixel)}"
            for _landmark, point in ordered_points
        )
        comment = (
            "COMMENT="
            f"template_id:{template.id};template_version:{template.version};"
            f"annotation_id:{annotation.id};revision:{annotation.revision_number};"
            "origin:top-left;y_axis:down;units:source_pixels"
        )
        if annotation.wing_image.scale_mm_per_pixel is not None:
            comment += f";scale_mm_per_pixel:{annotation.wing_image.scale_mm_per_pixel:.12g}"
        lines.extend(
            [
                f"ID={record.accession_number}",
                f"IMAGE={annotation.wing_image.original_filename}",
                comment,
            ]
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


__all__ = [
    "CSV_COLUMNS",
    "approved_records_for_template",
    "export_approved_csv",
    "export_approved_tps",
]
