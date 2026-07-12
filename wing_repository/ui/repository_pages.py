"""Read-only repository browsing and exact-template export pages."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from wing_repository.enums import AnnotationStatus, ReviewDecision
from wing_repository.errors import RepositoryError
from wing_repository.exports import (
    approved_records_for_template,
    export_approved_csv,
    export_approved_tps,
)
from wing_repository.models import (
    Annotation,
    AnnotationPoint,
    LandmarkTemplate,
    RepositoryRecord,
    Review,
    Taxon,
    User,
    WingImage,
)
from wing_repository.ui.common import (
    annotation_dataframe,
    annotation_overlay,
    format_image_scale,
)


def _approved_predicates() -> tuple[Any, ...]:
    """Return the defensive approval predicates shared by every page query."""

    return (
        Annotation.status == AnnotationStatus.APPROVED,
        Review.decision == ReviewDecision.APPROVE,
    )


def _approved_taxa(session: Session) -> list[Taxon]:
    """Return genera that have at least one consistently approved record."""

    statement = (
        select(Taxon)
        .join(Taxon.repository_records)
        .join(RepositoryRecord.annotation)
        .join(RepositoryRecord.review)
        .where(*_approved_predicates())
        .distinct()
        .order_by(Taxon.genus, Taxon.id)
    )
    return list(session.scalars(statement))


def _approved_templates(
    session: Session, *, taxon_id: int | None = None
) -> list[LandmarkTemplate]:
    """Return exact templates represented by approved repository records."""

    statement = (
        select(LandmarkTemplate)
        .join(Annotation, Annotation.template_id == LandmarkTemplate.id)
        .join(RepositoryRecord, RepositoryRecord.annotation_id == Annotation.id)
        .join(Review, Review.id == RepositoryRecord.review_id)
        .where(*_approved_predicates())
        .options(joinedload(LandmarkTemplate.taxon))
        .distinct()
        .order_by(LandmarkTemplate.taxon_id, LandmarkTemplate.version, LandmarkTemplate.id)
    )
    if taxon_id is not None:
        statement = statement.where(LandmarkTemplate.taxon_id == taxon_id)
    return list(session.scalars(statement))


def _record_statement() -> Select[tuple[RepositoryRecord]]:
    """Build the approved-only repository statement with display relationships."""

    return (
        select(RepositoryRecord)
        .join(RepositoryRecord.annotation)
        .join(RepositoryRecord.review)
        .where(*_approved_predicates())
        .options(
            joinedload(RepositoryRecord.taxon),
            joinedload(RepositoryRecord.review).joinedload(Review.reviewer),
            joinedload(RepositoryRecord.annotation)
            .joinedload(Annotation.template)
            .joinedload(LandmarkTemplate.taxon),
            joinedload(RepositoryRecord.annotation)
            .joinedload(Annotation.wing_image)
            .joinedload(WingImage.specimen),
            joinedload(RepositoryRecord.annotation)
            .selectinload(Annotation.points)
            .joinedload(AnnotationPoint.template_landmark),
        )
        .order_by(RepositoryRecord.accession_number)
    )


def _approved_records(
    session: Session,
    *,
    taxon_id: int | None = None,
    template_id: int | None = None,
) -> list[RepositoryRecord]:
    statement = _record_statement()
    if taxon_id is not None:
        statement = statement.where(RepositoryRecord.taxon_id == taxon_id)
    if template_id is not None:
        statement = statement.where(Annotation.template_id == template_id)
    return list(session.scalars(statement).unique())


def _reset_stale_selection(key: str, valid_values: Sequence[int | None]) -> None:
    """Clear a widget value whose upstream filter has made it invalid."""

    if st.session_state.get(key) not in valid_values:
        st.session_state[key] = None


def _template_label(template: LandmarkTemplate) -> str:
    return (
        f"{template.taxon.genus} | {template.name} | "
        f"version {template.version} | template ID {template.id}"
    )


def _record_table(records: Sequence[RepositoryRecord]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        annotation = record.annotation
        specimen = annotation.wing_image.specimen
        rows.append(
            {
                "accession": record.accession_number,
                "genus": record.taxon.genus,
                "specimen_code": specimen.specimen_code,
                "species": specimen.species_text or "",
                "locality_sample": (
                    f"{specimen.locality_sample_code or ''} "
                    f"{specimen.locality_sample_number or ''}/"
                    f"{specimen.locality_sample_size or ''}"
                ).strip(),
                "template_id": annotation.template_id,
                "template_version": annotation.template.version,
                "published": record.published_at,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "accession",
            "genus",
            "specimen_code",
            "species",
            "locality_sample",
            "template_id",
            "template_version",
            "published",
        ],
    )


def _render_record_detail(record: RepositoryRecord) -> None:
    annotation = record.annotation
    template = annotation.template
    image = annotation.wing_image
    specimen = image.specimen

    st.subheader(record.accession_number)
    st.caption(
        f"Approved repository record | {record.taxon.genus} | "
        f"template ID {template.id}, version {template.version}"
    )

    summary_columns = st.columns(4)
    summary_columns[0].metric("Genus", record.taxon.genus)
    summary_columns[1].metric("Specimen", specimen.specimen_code)
    summary_columns[2].metric("Template version", str(template.version))
    summary_columns[3].metric("Landmarks", str(len(annotation.points)))

    image_column, metadata_column = st.columns([3, 2])
    with image_column:
        st.markdown("#### Numbered landmark overlay")
        try:
            overlay = annotation_overlay(annotation)
        except RepositoryError as exc:
            st.warning(f"The preserved image could not be displayed: {exc}")
        else:
            st.image(
                overlay,
                caption=(
                    f"Original raster coordinate space: "
                    f"{annotation.image_width} x {annotation.image_height} pixels"
                ),
                width="stretch",
            )

    with metadata_column:
        st.markdown("#### Record metadata")
        st.write(f"**Template:** {_template_label(template)}")
        st.write(f"**Species text:** {specimen.species_text or 'Not supplied'}")
        st.write(
            "**Identification method:** "
            f"{specimen.species_identification_method.value if specimen.species_identification_method else 'Not supplied'}"
        )
        if specimen.genbank_accession:
            st.write(f"**GenBank accession:** {specimen.genbank_accession}")
        if specimen.taxonomist_name:
            st.write(f"**Taxonomist:** {specimen.taxonomist_name}")
        st.write(f"**Sex:** {specimen.sex or 'Not supplied'}")
        st.write(f"**Collection date:** {specimen.collection_date or 'Not supplied'}")
        st.write(f"**Collector:** {specimen.collector_name or 'Not supplied'}")
        st.write(f"**Country:** {specimen.country or 'Not supplied'}")
        st.write(f"**Locality:** {specimen.locality or 'Not supplied'}")
        st.write(
            "**Locality sample:** "
            f"{specimen.locality_sample_code or 'Not supplied'} "
            f"{specimen.locality_sample_number or '?'}/"
            f"{specimen.locality_sample_size or '?'}"
        )
        st.write(f"**Original filename:** {image.original_filename}")
        st.write(f"**Image SHA-256:** `{image.sha256}`")
        st.write(f"**Image scale:** {format_image_scale(image)}")
        st.write(f"**Approved by:** {record.review.reviewer.full_name}")
        st.write(f"**Published:** {record.published_at}")

    st.markdown("#### Preserved coordinates")
    st.caption(
        "Pixel coordinates refer to the encoded original raster. Normalized "
        "coordinates use x/image_width and y/image_height. Millimeter columns "
        "are derived from the saved image scale when calibrated."
    )
    coordinates = annotation_dataframe(annotation)
    st.dataframe(
        coordinates,
        hide_index=True,
        width="stretch",
        column_config={
            "landmark": st.column_config.NumberColumn("Landmark", format="%d"),
            "x_pixel": st.column_config.NumberColumn("X pixel", format="%.3f"),
            "y_pixel": st.column_config.NumberColumn("Y pixel", format="%.3f"),
            "x_normalized": st.column_config.NumberColumn(
                "X normalized", format="%.8f"
            ),
            "y_normalized": st.column_config.NumberColumn(
                "Y normalized", format="%.8f"
            ),
            "x_mm": st.column_config.NumberColumn("X mm", format="%.6f"),
            "y_mm": st.column_config.NumberColumn("Y mm", format="%.6f"),
        },
    )


def render_repository_browser(session: Session, _user: User) -> None:
    """Render approved records with genus and exact-template filters."""

    st.title("Repository browser")
    st.caption(
        "Only expert-approved records are visible. Template identity is shown "
        "explicitly and coordinate sets are never combined here."
    )

    taxa = _approved_taxa(session)
    if not taxa:
        st.info("No annotations have been approved for the reference repository yet.")
        return

    taxa_by_id = {taxon.id: taxon for taxon in taxa}
    genus_options: list[int | None] = [None, *taxa_by_id]
    _reset_stale_selection("repository_genus_id", genus_options)

    filter_columns = st.columns(2)
    with filter_columns[0]:
        selected_taxon_id = st.selectbox(
            "Genus",
            genus_options,
            key="repository_genus_id",
            format_func=lambda value: (
                "All approved genera"
                if value is None
                else taxa_by_id[value].genus
            ),
        )

    templates = _approved_templates(session, taxon_id=selected_taxon_id)
    templates_by_id = {template.id: template for template in templates}
    template_options: list[int | None] = [None, *templates_by_id]
    _reset_stale_selection("repository_template_id", template_options)
    with filter_columns[1]:
        selected_template_id = st.selectbox(
            "Exact landmark template",
            template_options,
            key="repository_template_id",
            format_func=lambda value: (
                "All exact templates"
                if value is None
                else _template_label(templates_by_id[value])
            ),
        )

    records = _approved_records(
        session,
        taxon_id=selected_taxon_id,
        template_id=selected_template_id,
    )
    if not records:
        st.info("No approved repository records match these filters.")
        return

    st.dataframe(
        _record_table(records), hide_index=True, width="stretch"
    )

    records_by_id = {record.id: record for record in records}
    record_ids = list(records_by_id)
    if st.session_state.get("repository_record_id") not in record_ids:
        st.session_state["repository_record_id"] = record_ids[0]
    selected_record_id = st.selectbox(
        "Inspect accession",
        record_ids,
        key="repository_record_id",
        format_func=lambda value: records_by_id[value].accession_number,
    )
    _render_record_detail(records_by_id[selected_record_id])


def render_export(session: Session, _user: User) -> None:
    """Render CSV and TPS downloads for one exact template identity."""

    st.title("TPS and CSV export")
    st.warning(
        "Choose one exact landmark-template version. Version 0.1 refuses to "
        "combine records from different template IDs."
    )

    taxa = _approved_taxa(session)
    if not taxa:
        st.info("No approved repository records are available to export.")
        return

    taxa_by_id = {taxon.id: taxon for taxon in taxa}
    genus_options: list[int | None] = [None, *taxa_by_id]
    _reset_stale_selection("export_genus_id", genus_options)
    selected_taxon_id = st.selectbox(
        "Genus",
        genus_options,
        key="export_genus_id",
        format_func=lambda value: (
            "Select a genus" if value is None else taxa_by_id[value].genus
        ),
    )
    if selected_taxon_id is None:
        return

    templates = _approved_templates(session, taxon_id=selected_taxon_id)
    templates_by_id = {template.id: template for template in templates}
    template_options: list[int | None] = [None, *templates_by_id]
    _reset_stale_selection("export_template_id", template_options)
    selected_template_id = st.selectbox(
        "Exact landmark template",
        template_options,
        key="export_template_id",
        format_func=lambda value: (
            "Select one exact template"
            if value is None
            else _template_label(templates_by_id[value])
        ),
    )
    if selected_template_id is None:
        return

    template, records = approved_records_for_template(
        session, template_id=selected_template_id
    )
    if not records:
        st.info("This exact template currently has no approved records.")
        return

    st.success(
        f"{len(records)} approved record(s) selected for template ID "
        f"{template.id}, version {template.version}."
    )
    st.caption(
        "CSV contains accession and specimen context plus preserved pixel, "
        "normalized, and calibrated millimeter coordinates when an image scale "
        "is saved. TPS contains the original-raster pixel landmarks in template "
        "ordinal order."
    )

    csv_text = export_approved_csv(session, template_id=template.id)
    tps_text = export_approved_tps(session, template_id=template.id)
    filename_stem = (
        f"wbr_hym_{template.taxon.genus_code.lower()}_"
        f"template_{template.id}_v{template.version}"
    )
    download_columns = st.columns(2)
    download_columns[0].download_button(
        "Download CSV",
        data=csv_text.encode("utf-8"),
        file_name=f"{filename_stem}.csv",
        mime="text/csv; charset=utf-8",
        width="stretch",
    )
    download_columns[1].download_button(
        "Download TPS",
        data=tps_text.encode("utf-8"),
        file_name=f"{filename_stem}.tps",
        mime="text/plain; charset=utf-8",
        width="stretch",
    )


__all__ = ["render_export", "render_repository_browser"]
