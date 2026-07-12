"""Streamlit page for published Apis reference analysis."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from wing_repository.analysis_services import (
    NAWROCKA_CITATION,
    OLEKSA_CITATION,
    SINGLE_WING_WARNING,
    WORKFLOW_CITATION,
    active_query_annotations,
    published_shape_match_rows,
    run_published_apis_reference_analysis,
)
from wing_repository.models import Annotation, User, WingAnalysisRun
from wing_repository.ui.common import format_template


def _annotation_label(annotation: Annotation) -> str:
    specimen = annotation.wing_image.specimen
    return (
        f"{specimen.specimen_code} · {annotation.status.value} · "
        f"{format_template(annotation.template)} · revision {annotation.revision_number}"
    )


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _render_scope() -> None:
    st.title("Published Apis Reference Analysis")
    st.subheader("Preliminary single-wing wing-shape analysis")
    st.warning(SINGLE_WING_WARNING)
    st.table(
        pd.DataFrame(
            [
                ("Taxon", "Apis mellifera"),
                ("Wing analysed", "Right forewing"),
                ("Landmarks", "19 fixed landmarks"),
                ("Reference", "Oleksa et al. (2023), Zenodo 7244070"),
                ("Analysis", "Shape only; physical size excluded"),
                ("Input mode", "Single wing — preliminary result"),
            ],
            columns=["Field", "Value"],
        )
    )
    st.caption(
        "This module is not species identification and does not make molecular, "
        "genomic or definitive lineage claims."
    )


def _region_table(run: WingAnalysisRun) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rank": row.rank,
                "Reference group": row.reference_group,
                "Classification probability": _percent(row.probability),
                "Reference samples": row.reference_sample_count,
                "Interpretation": row.interpretation,
            }
            for row in sorted(run.region_probabilities, key=lambda item: item.rank)
        ]
    )


def _lineage_table(run: WingAnalysisRun) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rank": row.rank,
                "Predicted lineage affinity": row.lineage_code,
                "Classification probability": _percent(row.probability),
                "Reference samples": row.reference_sample_count,
                "Decision": row.interpretation,
            }
            for row in sorted(run.lineage_probabilities, key=lambda item: item.rank)
        ]
    )


def _nearest_table(run: WingAnalysisRun) -> pd.DataFrame:
    frame = pd.DataFrame(published_shape_match_rows(run))
    if not frame.empty:
        frame["Procrustes distance"] = frame["Procrustes distance"].map(lambda value: f"{value:.6f}")
        frame["Similarity percentile"] = frame["Similarity percentile"].map(lambda value: f"{value:.1f}")
    return frame[
        [
            "Rank",
            "Source taxon",
            "Published source record",
            "Source sample",
            "Country",
            "Procrustes distance",
            "Similarity percentile",
        ]
    ] if not frame.empty else frame


def _render_result(run: WingAnalysisRun) -> None:
    if run.warning_text:
        st.info(run.warning_text)
    st.subheader("SECTION 1 — Geographical wing-shape affinity")
    st.dataframe(_region_table(run), width="stretch", hide_index=True)

    st.subheader("SECTION 2 — Evolutionary-lineage wing-shape affinity")
    st.dataframe(_lineage_table(run), width="stretch", hide_index=True)
    if run.lineage_probabilities:
        top = sorted(run.lineage_probabilities, key=lambda item: item.rank)[0]
        st.caption(
            "The submitted wing shows strongest geometric affinity to "
            f"Lineage {top.lineage_code} reference phenotypes."
        )

    st.subheader("SECTION 3 — Closest published forewing shapes")
    st.dataframe(_nearest_table(run), width="stretch", hide_index=True)
    st.caption("All rows in this section are External published reference records, not WBR accessions.")
    st.markdown(
        "\n".join(
            [
                OLEKSA_CITATION,
                NAWROCKA_CITATION,
                WORKFLOW_CITATION,
            ]
        )
    )


def render_published_apis_reference_analysis(session: Session, user: User) -> None:
    """Render the Apis published-reference analysis page."""

    _render_scope()
    candidates = active_query_annotations(session, user)
    if not candidates:
        st.info(
            "No complete 19-landmark Apis right-forewing annotation is available "
            "for this account. The v1 10-landmark teaching template cannot be analysed."
        )
        return
    annotation_by_id = {annotation.id: annotation for annotation in candidates}
    selected_annotation_id = st.selectbox(
        "Query annotation",
        list(annotation_by_id),
        format_func=lambda annotation_id: _annotation_label(annotation_by_id[annotation_id]),
    )
    nearest_limit = st.slider("Closest published shapes to show", 1, 20, 10)
    if st.button("Run published Apis reference analysis", type="primary"):
        run = run_published_apis_reference_analysis(
            session,
            user,
            annotation_id=int(selected_annotation_id),
            nearest_limit=int(nearest_limit),
        )
        st.session_state["wbr_last_apis_analysis_run_id"] = run.id
        st.toast("Published Apis reference analysis completed.")
        st.rerun()

    run_id = st.session_state.get("wbr_last_apis_analysis_run_id")
    if isinstance(run_id, int):
        run = session.get(WingAnalysisRun, run_id)
        if run is not None:
            _render_result(run)


__all__ = ["render_published_apis_reference_analysis"]
