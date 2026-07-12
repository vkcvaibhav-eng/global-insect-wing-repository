"""Minimal administrator controls for the Version 0.1 assignment scope."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from wing_repository.enums import AnnotationStatus, Role, TemplateStatus
from wing_repository.models import (
    Annotation,
    Assignment,
    LandmarkTemplate,
    RepositoryRecord,
    User,
)
from wing_repository.services import (
    approve_user_account,
    create_assignment,
    create_user_account,
    deactivate_assignment,
    import_bundled_standard_template,
)
from wing_repository.ui.common import format_template


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _assignment_rows(assignments: list[Assignment]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "assignment_id": assignment.id,
                "student": assignment.student.full_name,
                "email": assignment.student.email,
                "genus": assignment.taxon.genus,
                "template_id": assignment.template_id,
                "template_version": assignment.template.version,
                "active": assignment.is_active,
                "assigned_at": assignment.assigned_at,
                "ended_at": assignment.ended_at,
            }
            for assignment in assignments
        ]
    )


def _pending_user_rows(users: list[User]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "user_id": pending_user.id,
                "full_name": pending_user.full_name,
                "email": pending_user.email,
                "role": pending_user.role.value.replace("_", " "),
                "requested_at": pending_user.created_at,
            }
            for pending_user in users
        ]
    )


def render_administration(session: Session, user: User) -> None:
    st.title("Administration")
    st.caption(
        "Version 0.1 administration is intentionally limited to inspecting "
        "the repository and assigning a student to one exact published template."
    )

    metrics = st.columns(4)
    metrics[0].metric("Users", _count(session, User))
    metrics[1].metric("Templates", _count(session, LandmarkTemplate))
    metrics[2].metric(
        "Awaiting review",
        int(
            session.scalar(
                select(func.count(Annotation.id)).where(
                    Annotation.status == AnnotationStatus.SUBMITTED
                )
            )
            or 0
        ),
    )
    metrics[3].metric("Approved records", _count(session, RepositoryRecord))

    st.subheader("Approve account signups")
    pending_accounts = list(
        session.scalars(
            select(User)
            .where(
                User.role.in_([Role.STUDENT, Role.EXPERT_REVIEWER]),
                User.is_active.is_(False),
            )
            .order_by(User.created_at.asc(), User.id.asc())
        )
    )
    if not pending_accounts:
        st.info("No account signup requests are waiting for approval.")
    else:
        st.dataframe(
            _pending_user_rows(pending_accounts),
            hide_index=True,
            width="stretch",
        )
        pending_by_id = {
            pending_user.id: pending_user for pending_user in pending_accounts
        }
        selected_pending_id = st.selectbox(
            "Pending account to approve",
            list(pending_by_id),
            format_func=lambda user_id: (
                f"{pending_by_id[user_id].full_name} · "
                f"{pending_by_id[user_id].email} · "
                f"{pending_by_id[user_id].role.value.replace('_', ' ').title()}"
            ),
        )
        if st.button("Approve selected account", type="primary"):
            approved = approve_user_account(
                session,
                user,
                user_id=selected_pending_id,
            )
            st.toast(f"Approved {approved.email}.")
            st.rerun()

    st.subheader("Create user account")
    st.caption(
        "Optional fallback for administrators: create a student or reviewer "
        "directly. Share temporary passwords outside the app; Version 0.1 does "
        "not send email."
    )
    with st.form("create_user_form", clear_on_submit=True):
        new_full_name = st.text_input("Full name")
        new_email = st.text_input("Email")
        new_role = st.selectbox(
            "Role",
            [Role.STUDENT, Role.EXPERT_REVIEWER],
            format_func=lambda role: role.value.replace("_", " ").title(),
        )
        new_password = st.text_input(
            "Temporary password",
            type="password",
            help="Use at least 12 characters. The password is hashed before storage.",
        )
        create_user_submitted = st.form_submit_button(
            "Create account",
            type="primary",
        )
    if create_user_submitted:
        created_user = create_user_account(
            session,
            user,
            email=new_email,
            full_name=new_full_name,
            role=new_role,
            password=new_password,
        )
        st.toast(f"Created {created_user.email}.")
        st.rerun()

    students = list(
        session.scalars(
            select(User)
            .where(
                User.role == Role.STUDENT,
                User.is_active.is_(True),
                ~User.id.in_(
                    select(Assignment.student_id).where(
                        Assignment.is_active.is_(True)
                    )
                ),
            )
            .order_by(User.full_name, User.id)
        )
    )
    templates = list(
        session.scalars(
            select(LandmarkTemplate)
            .where(LandmarkTemplate.status == TemplateStatus.PUBLISHED)
            .options(joinedload(LandmarkTemplate.taxon))
            .order_by(
                LandmarkTemplate.taxon_id,
                LandmarkTemplate.version,
                LandmarkTemplate.id,
            )
        )
    )

    st.subheader("Create assignment")
    if not templates:
        st.info(
            "At least one published landmark template is required. The "
            "bundled standard Apis 19-landmark template can be loaded now."
        )
        if st.button("Load bundled Apis 19-landmark template", type="primary"):
            template = import_bundled_standard_template(session, user)
            st.toast(f"Loaded {format_template(template)}.")
            st.rerun()
    elif not students:
        st.info("Every active student already has an active assignment.")
    else:
        students_by_id = {student.id: student for student in students}
        templates_by_id = {template.id: template for template in templates}
        with st.form("create_assignment_form"):
            selected_student_id = st.selectbox(
                "Student",
                list(students_by_id),
                format_func=lambda student_id: (
                    f"{students_by_id[student_id].full_name} · "
                    f"{students_by_id[student_id].email}"
                ),
            )
            selected_template_id = st.selectbox(
                "Exact published template",
                list(templates_by_id),
                format_func=lambda template_id: format_template(
                    templates_by_id[template_id]
                ),
            )
            submitted = st.form_submit_button("Assign student", type="primary")
        if submitted:
            template = templates_by_id[selected_template_id]
            assignment = create_assignment(
                session,
                user,
                student_id=selected_student_id,
                taxon_id=template.taxon_id,
                template_id=selected_template_id,
            )
            st.toast(f"Assignment {assignment.id} created.")
            st.rerun()

    assignments = list(
        session.scalars(
            select(Assignment)
            .options(
                joinedload(Assignment.student),
                joinedload(Assignment.taxon),
                joinedload(Assignment.template),
            )
            .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
        )
    )
    st.subheader("Assignment history")
    if not assignments:
        st.info("No assignments have been created.")
        return
    st.dataframe(_assignment_rows(assignments), hide_index=True, width="stretch")
    active_assignments = [item for item in assignments if item.is_active]
    if active_assignments:
        active_by_id = {assignment.id: assignment for assignment in active_assignments}
        selected_assignment_id = st.selectbox(
            "Active assignment to end",
            list(active_by_id),
            format_func=lambda assignment_id: (
                f"{active_by_id[assignment_id].student.full_name} · "
                f"{active_by_id[assignment_id].taxon.genus} · "
                f"template v{active_by_id[assignment_id].template.version}"
            ),
        )
        if st.button("Deactivate selected assignment"):
            deactivate_assignment(
                session, user, assignment_id=selected_assignment_id
            )
            st.toast("Assignment ended; existing scientific records were preserved.")
            st.rerun()


__all__ = ["render_administration"]
