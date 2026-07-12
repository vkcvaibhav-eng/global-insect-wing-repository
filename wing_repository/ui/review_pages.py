"""Expert review queue and immutable annotation decision UI."""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from wing_repository.models import Annotation, User
from wing_repository.services import (
    approve_annotation,
    list_submitted_annotations,
    return_annotation,
)
from wing_repository.ui.common import (
    annotation_dataframe,
    annotation_overlay,
    format_image_scale,
    format_template,
)


def _queue_label(annotation: Annotation) -> str:
    specimen = annotation.wing_image.specimen
    return (
        f"{specimen.specimen_code} · {annotation.template.taxon.genus} · "
        f"template v{annotation.template.version} · revision {annotation.revision_number}"
    )


def render_expert_review(session: Session, user: User) -> None:
    st.title("Expert review")
    st.caption(
        "Review the immutable original-image coordinate set and its exact "
        "template version. Approval and accession creation are one transaction."
    )
    queue = list_submitted_annotations(session, user)
    if not queue:
        st.info("There are no submitted annotations awaiting review.")
        return

    queue_by_id = {annotation.id: annotation for annotation in queue}
    selected_annotation_id = st.selectbox(
        "Submitted annotation",
        list(queue_by_id),
        format_func=lambda annotation_id: _queue_label(
            queue_by_id[annotation_id]
        ),
    )
    annotation = queue_by_id[selected_annotation_id]
    specimen = annotation.wing_image.specimen
    st.subheader(_queue_label(annotation))
    summary = st.columns(4)
    summary[0].metric("Contributor", annotation.contributor.full_name)
    summary[1].metric("Genus", annotation.template.taxon.genus)
    summary[2].metric("Template version", annotation.template.version)
    summary[3].metric("Points", len(annotation.points))

    image_column, metadata_column = st.columns((3, 2))
    with image_column:
        overlay = annotation_overlay(annotation)
        st.image(
            overlay,
            caption=(
                f"{annotation.wing_image.original_filename} · source raster "
                f"{annotation.image_width} × {annotation.image_height} px"
            ),
            width="stretch",
        )
    with metadata_column:
        st.write(f"**Template:** {format_template(annotation.template)}")
        st.write(f"**Specimen code:** {specimen.specimen_code}")
        st.write(f"**Species:** {specimen.species_text or 'Not supplied'}")
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
        st.write(
            f"**Voucher:** {specimen.voucher_institution or 'Not supplied'} / "
            f"{specimen.voucher_code or 'Not supplied'}"
        )
        st.write(f"**Image SHA-256:** `{annotation.wing_image.sha256}`")
        st.write(f"**Image scale:** {format_image_scale(annotation.wing_image)}")
        st.write(f"**Submitted:** {annotation.submitted_at}")

    st.subheader("Preserved coordinates")
    st.dataframe(
        annotation_dataframe(annotation),
        hide_index=True,
        width="stretch",
        column_config={
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

    with st.form(f"review_decision_{annotation.id}"):
        comments = st.text_area(
            "Reviewer comments",
            help="Comments are required when returning an annotation.",
            max_chars=10_000,
        )
        approve_column, return_column = st.columns(2)
        approved = approve_column.form_submit_button(
            "Approve and issue accession",
            type="primary",
            width="stretch",
        )
        returned = return_column.form_submit_button(
            "Return for revision",
            width="stretch",
        )

    if approved:
        record = approve_annotation(
            session,
            user,
            annotation_id=annotation.id,
            comments=comments,
        )
        st.toast(f"Approved as {record.accession_number}.")
        st.rerun()
    if returned:
        return_annotation(
            session,
            user,
            annotation_id=annotation.id,
            comments=comments,
        )
        st.toast("Annotation returned; the reviewed revision remains preserved.")
        st.rerun()


__all__ = ["render_expert_review"]
