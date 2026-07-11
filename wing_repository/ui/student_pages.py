"""Student/contributor pages for metadata, upload, digitization, and status."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from streamlit_image_coordinates import streamlit_image_coordinates

from wing_repository.coordinates import click_event_token, coordinate_from_click_event
from wing_repository.enums import AnnotationStatus
from wing_repository.errors import NotFoundError, RepositoryError, ValidationError
from wing_repository.models import (
    Annotation,
    AnnotationPoint,
    LandmarkTemplate,
    Specimen,
    User,
    WingImage,
)
from wing_repository.services import (
    attach_wing_image,
    clone_returned_annotation,
    create_draft_annotation,
    create_specimen,
    delete_annotation_point,
    get_active_assignment,
    list_student_annotations,
    place_annotation_point,
    submit_annotation,
    undo_last_point,
)
from wing_repository.ui.common import (
    annotation_dataframe,
    annotation_overlay,
    format_template,
    image_store,
    move_to_page,
)


def _optional_float(value: str, field_name: str) -> float | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a number or left blank.") from exc


def _assignment_or_notice(session: Session, user: User):
    try:
        return get_active_assignment(session, user)
    except NotFoundError:
        st.warning(
            "No active genus/template assignment is available. Ask an "
            "administrator to assign one before creating records."
        )
        return None


def render_student_dashboard(session: Session, user: User) -> None:
    st.title("Student dashboard")
    assignment = _assignment_or_notice(session, user)
    if assignment is not None:
        st.subheader(f"Assigned genus: {assignment.taxon.genus}")
        st.write(f"Order: **{assignment.taxon.order_name}**")
        st.write(f"Exact template: **{format_template(assignment.template)}**")
        st.caption(
            "The exact template identity is pinned to every specimen and "
            "annotation. A newer version is never substituted automatically."
        )

    counts = dict(
        session.execute(
            select(Annotation.status, func.count(Annotation.id))
            .where(Annotation.contributor_id == user.id)
            .group_by(Annotation.status)
        ).all()
    )
    columns = st.columns(4)
    for column, status in zip(
        columns,
        (
            AnnotationStatus.DRAFT,
            AnnotationStatus.SUBMITTED,
            AnnotationStatus.RETURNED,
            AnnotationStatus.APPROVED,
        ),
        strict=True,
    ):
        column.metric(status.value.title(), counts.get(status, 0))

    st.subheader("Version 0.1 workflow")
    st.markdown(
        "1. Complete the specimen metadata form.\n"
        "2. Upload the specimen's original right-forewing PNG or JPEG.\n"
        "3. Place every landmark in the displayed template order.\n"
        "4. Submit the complete coordinate set for expert review.\n"
        "5. If returned, create a new revision; the reviewed revision stays preserved."
    )


def render_metadata_form(session: Session, user: User) -> None:
    st.title("Specimen metadata form")
    assignment = _assignment_or_notice(session, user)
    if assignment is None:
        return
    st.info(
        f"This record will be fixed to {assignment.taxon.order_name} / "
        f"{assignment.taxon.genus} and template v{assignment.template.version}."
    )

    with st.form("specimen_metadata_form", clear_on_submit=False):
        left, right = st.columns(2)
        with left:
            specimen_code = st.text_input(
                "Contributor specimen code *",
                help="A stable code unique within your account.",
                max_chars=120,
            )
            species_text = st.text_input(
                "Species identification (optional)", max_chars=200
            )
            sex = st.selectbox(
                "Sex (optional)",
                ("", "female", "male", "worker", "queen", "unknown"),
            )
            collection_date = st.date_input(
                "Collection date (optional)", value=None, max_value=date.today()
            )
            collector_name = st.text_input("Collector (optional)", max_chars=200)
        with right:
            country = st.text_input("Country (optional)", max_chars=100)
            locality = st.text_area("Locality (optional)")
            coordinate_columns = st.columns(2)
            latitude_text = coordinate_columns[0].text_input(
                "Latitude", placeholder="e.g. 12.9716"
            )
            longitude_text = coordinate_columns[1].text_input(
                "Longitude", placeholder="e.g. 77.5946"
            )
            voucher_institution = st.text_input(
                "Voucher institution (optional)", max_chars=200
            )
            voucher_code = st.text_input("Voucher code (optional)", max_chars=120)
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Save specimen metadata", type="primary")

    if submitted:
        specimen = create_specimen(
            session,
            user,
            specimen_code=specimen_code,
            assignment_id=assignment.id,
            species_text=species_text,
            sex=sex,
            collection_date=collection_date,
            country=country,
            locality=locality,
            latitude=_optional_float(latitude_text, "Latitude"),
            longitude=_optional_float(longitude_text, "Longitude"),
            collector_name=collector_name,
            voucher_institution=voucher_institution,
            voucher_code=voucher_code,
            notes=notes,
        )
        st.session_state["wbr_last_specimen_id"] = specimen.id
        st.toast(f"Specimen {specimen.specimen_code} was saved.")
        move_to_page("Wing-image upload")


def render_upload(session: Session, user: User) -> None:
    st.title("Wing-image upload")
    st.caption(
        "Original bytes are validated, hashed, and saved once. Version 0.1 "
        "accepts one right-forewing PNG or JPEG per specimen."
    )
    specimens = list(
        session.scalars(
            select(Specimen)
            .where(Specimen.contributor_id == user.id)
            .options(selectinload(Specimen.wing_image), selectinload(Specimen.taxon))
            .order_by(Specimen.created_at.desc())
        )
    )
    eligible = [specimen for specimen in specimens if specimen.wing_image is None]
    if not eligible:
        st.info("Create specimen metadata first, or all of your specimens already have images.")
        return

    preferred_id = st.session_state.get("wbr_last_specimen_id")
    default_index = next(
        (index for index, specimen in enumerate(eligible) if specimen.id == preferred_id),
        0,
    )
    eligible_by_id = {specimen.id: specimen for specimen in eligible}
    selected_specimen_id = st.selectbox(
        "Specimen",
        list(eligible_by_id),
        index=default_index,
        format_func=lambda specimen_id: (
            f"{eligible_by_id[specimen_id].specimen_code} · "
            f"{eligible_by_id[specimen_id].taxon.genus}"
        ),
    )
    selected = eligible_by_id[selected_specimen_id]
    uploaded_file = st.file_uploader(
        "Original right-forewing image",
        type=("png", "jpg", "jpeg"),
        accept_multiple_files=False,
    )
    if uploaded_file is not None:
        st.image(uploaded_file, caption=uploaded_file.name, width="stretch")
    if st.button(
        "Preserve original and attach image",
        type="primary",
        disabled=uploaded_file is None,
    ):
        assert uploaded_file is not None
        wing_image = attach_wing_image(
            session,
            user,
            image_store(),
            specimen_id=selected.id,
            image_bytes=uploaded_file.getvalue(),
            original_filename=uploaded_file.name,
        )
        st.session_state["wbr_last_wing_image_id"] = wing_image.id
        st.toast(
            f"Preserved {wing_image.original_filename} "
            f"({wing_image.image_width} × {wing_image.image_height} px)."
        )
        move_to_page("Manual landmark digitization")


def _owned_wing_images(session: Session, user: User) -> list[WingImage]:
    return list(
        session.scalars(
            select(WingImage)
            .join(WingImage.specimen)
            .where(Specimen.contributor_id == user.id)
            .options(
                selectinload(WingImage.specimen).selectinload(Specimen.taxon),
                selectinload(WingImage.annotations),
            )
            .order_by(WingImage.uploaded_at.desc())
        )
    )


def _draft_annotations(session: Session, user: User) -> list[Annotation]:
    return list(
        session.scalars(
            select(Annotation)
            .where(
                Annotation.contributor_id == user.id,
                Annotation.status == AnnotationStatus.DRAFT,
            )
            .options(
                selectinload(Annotation.points).selectinload(
                    AnnotationPoint.template_landmark
                ),
                selectinload(Annotation.template).selectinload(
                    LandmarkTemplate.landmarks
                ),
                selectinload(Annotation.template).selectinload(
                    LandmarkTemplate.taxon
                ),
                selectinload(Annotation.wing_image).selectinload(WingImage.specimen),
            )
            .order_by(Annotation.updated_at.desc())
        )
    )


def _annotation_label(annotation: Annotation) -> str:
    specimen = annotation.wing_image.specimen
    return (
        f"{specimen.specimen_code} · {annotation.template.taxon.genus} · "
        f"template v{annotation.template.version} · revision {annotation.revision_number}"
    )


def _create_or_open_draft(session: Session, user: User) -> None:
    images = [image for image in _owned_wing_images(session, user) if not image.annotations]
    if not images:
        st.info("Upload a wing image before starting an annotation.")
        return
    images_by_id = {image.id: image for image in images}
    selected_image_id = st.selectbox(
        "Wing image",
        list(images_by_id),
        format_func=lambda image_id: (
            f"{images_by_id[image_id].specimen.specimen_code} · "
            f"{images_by_id[image_id].original_filename}"
        ),
        key="wbr_new_draft_image",
    )
    if st.button("Create or open draft", key="wbr_create_draft"):
        annotation = create_draft_annotation(
            session, user, wing_image_id=selected_image_id
        )
        st.session_state["wbr_selected_annotation_id"] = annotation.id
        st.rerun()


def render_digitization(session: Session, user: User) -> None:
    st.title("Manual landmark digitization")
    st.warning(
        "Use the current wide view for placement. Fine zoom, pan, and direct "
        "dragging require the planned custom TypeScript digitizer component."
    )
    drafts = _draft_annotations(session, user)
    if not drafts:
        _create_or_open_draft(session, user)
        return
    with st.expander("Start another image", expanded=False):
        _create_or_open_draft(session, user)

    selected_id = st.session_state.get("wbr_selected_annotation_id")
    default_index = next(
        (index for index, item in enumerate(drafts) if item.id == selected_id), 0
    )
    drafts_by_id = {draft.id: draft for draft in drafts}
    selected_annotation_id = st.selectbox(
        "Draft annotation",
        list(drafts_by_id),
        index=default_index,
        format_func=lambda annotation_id: _annotation_label(
            drafts_by_id[annotation_id]
        ),
        key="wbr_draft_selector",
    )
    annotation = drafts_by_id[selected_annotation_id]
    st.session_state["wbr_selected_annotation_id"] = annotation.id

    landmarks = sorted(annotation.template.landmarks, key=lambda item: item.ordinal)
    placed_by_landmark = {
        point.template_landmark_id: point for point in annotation.points
    }
    next_landmark = next(
        (
            landmark
            for landmark in landmarks
            if landmark.id not in placed_by_landmark
        ),
        None,
    )

    st.write(f"**{format_template(annotation.template)}**")
    progress = len(annotation.points) / len(landmarks) if landmarks else 0.0
    st.progress(progress, text=f"{len(annotation.points)} of {len(landmarks)} points saved")
    if next_landmark is not None:
        st.info(
            f"Place landmark {next_landmark.ordinal}: **{next_landmark.label}** — "
            f"{next_landmark.description or 'No description supplied.'}"
        )
    else:
        st.success("The exact template point set is complete and ready to submit.")

    overlay = annotation_overlay(annotation)
    event = streamlit_image_coordinates(
        overlay,
        width=overlay.width,
        key=f"digitizer_{annotation.id}",
    )
    if event is not None:
        token = click_event_token(event)
        token_key = f"wbr_last_click_{annotation.id}"
        if token != st.session_state.get(token_key):
            # Record the token before any rerun/error so Undo cannot replay the
            # component's prior event and silently re-add a point.
            st.session_state[token_key] = token
            if next_landmark is None:
                st.toast("All template landmarks are already placed.")
            else:
                coordinate = coordinate_from_click_event(
                    event,
                    original_width=annotation.image_width,
                    original_height=annotation.image_height,
                )
                place_annotation_point(
                    session,
                    user,
                    annotation_id=annotation.id,
                    template_landmark_id=next_landmark.id,
                    x_pixel=coordinate.x_pixel,
                    y_pixel=coordinate.y_pixel,
                    replace_existing=False,
                )
                st.rerun()

    controls = st.columns((1, 2, 1))
    with controls[0]:
        if st.button(
            "Undo last",
            disabled=not annotation.points,
            width="stretch",
        ):
            undo_last_point(session, user, annotation_id=annotation.id)
            st.rerun()
    with controls[1]:
        placed_landmarks = sorted(
            (point.template_landmark for point in annotation.points),
            key=lambda item: item.ordinal,
        )
        placed_landmarks_by_id = {
            landmark.id: landmark for landmark in placed_landmarks
        }
        selected_landmark_id: int | None = st.selectbox(
            "Delete/replace landmark",
            list(placed_landmarks_by_id),
            format_func=lambda landmark_id: (
                f"{placed_landmarks_by_id[landmark_id].ordinal}: "
                f"{placed_landmarks_by_id[landmark_id].label}"
            ),
            index=None,
            placeholder="Choose a saved point",
            label_visibility="collapsed",
        )
        if st.button(
            "Delete selected point",
            disabled=selected_landmark_id is None,
            width="stretch",
        ):
            assert selected_landmark_id is not None
            delete_annotation_point(
                session,
                user,
                annotation_id=annotation.id,
                template_landmark_id=selected_landmark_id,
            )
            st.rerun()
    with controls[2]:
        if st.button(
            "Submit for review",
            type="primary",
            disabled=len(annotation.points) != len(landmarks),
            width="stretch",
        ):
            submit_annotation(session, user, annotation_id=annotation.id)
            st.toast("Annotation submitted for expert review.")
            move_to_page("My submissions")

    table = annotation_dataframe(annotation)
    st.dataframe(
        table.style.format(
            {
                "x_pixel": "{:.3f}",
                "y_pixel": "{:.3f}",
                "x_normalized": "{:.8f}",
                "y_normalized": "{:.8f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )


def _submission_rows(annotations: list[Annotation]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "specimen": annotation.wing_image.specimen.specimen_code,
                "genus": annotation.template.taxon.genus,
                "template_version": annotation.template.version,
                "revision": annotation.revision_number,
                "status": annotation.status.value,
                "points": len(annotation.points),
                "submitted_at": annotation.submitted_at,
                "accession": (
                    annotation.repository_record.accession_number
                    if annotation.repository_record is not None
                    else None
                ),
            }
            for annotation in annotations
        ]
    )


def render_submissions(session: Session, user: User) -> None:
    st.title("My submissions")
    annotations = list_student_annotations(session, user)
    if not annotations:
        st.info("No annotation revisions have been created yet.")
        return
    st.dataframe(_submission_rows(annotations), width="stretch", hide_index=True)
    annotations_by_id = {annotation.id: annotation for annotation in annotations}
    selected_annotation_id = st.selectbox(
        "Inspect annotation revision",
        list(annotations_by_id),
        format_func=lambda annotation_id: (
            f"{_annotation_label(annotations_by_id[annotation_id])} · "
            f"{annotations_by_id[annotation_id].status.value}"
        ),
    )
    selected = annotations_by_id[selected_annotation_id]
    st.write(
        f"Status: **{selected.status.value.title()}** · "
        f"{len(selected.points)}/{len(selected.template.landmarks)} points"
    )
    if selected.review is not None:
        st.write(
            f"Expert decision: **{selected.review.decision.value.title()}**"
        )
        if selected.review.comments:
            st.info(selected.review.comments)
    if selected.repository_record is not None:
        st.success(
            f"Permanent accession: {selected.repository_record.accession_number}"
        )

    overlay = annotation_overlay(selected)
    st.image(overlay, caption=_annotation_label(selected), width="stretch")
    st.dataframe(
        annotation_dataframe(selected), width="stretch", hide_index=True
    )

    if selected.status is AnnotationStatus.DRAFT:
        if st.button("Resume this draft", type="primary"):
            st.session_state["wbr_selected_annotation_id"] = selected.id
            move_to_page("Manual landmark digitization")
    elif selected.status is AnnotationStatus.RETURNED:
        if st.button("Create editable revision", type="primary"):
            revision = clone_returned_annotation(
                session, user, annotation_id=selected.id
            )
            st.session_state["wbr_selected_annotation_id"] = revision.id
            move_to_page("Manual landmark digitization")
    elif selected.status is AnnotationStatus.SUBMITTED:
        st.caption("This submitted revision is immutable while awaiting review.")
    else:
        st.caption("This approved revision and its accession are permanent.")


__all__ = [
    "render_digitization",
    "render_metadata_form",
    "render_student_dashboard",
    "render_submissions",
    "render_upload",
]
