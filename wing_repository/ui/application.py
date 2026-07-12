"""Authenticated Streamlit application shell and role-aware navigation."""

from __future__ import annotations

from collections.abc import Callable
import logging
import re

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.db import SessionLocal, engine
from wing_repository.bootstrap import ensure_database_ready
from wing_repository.config import get_settings
from wing_repository.enums import Role
from wing_repository.errors import RepositoryError, ValidationError
from wing_repository.models import User
from wing_repository.security import normalize_email, verify_password
from wing_repository.services import request_student_signup
from wing_repository.ui.navigation import (
    CURRENT_PAGE_KEY,
    apply_queued_page_navigation,
)

PageRenderer = Callable[[Session, User], None]
logger = logging.getLogger(__name__)


def _safe_error_detail(exc: Exception) -> str:
    """Return a useful database startup error without leaking URL passwords."""

    detail = f"{type(exc).__name__}: {exc}"
    return re.sub(
        r"(?P<scheme>postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+):[^@\s]+@",
        r"\g<scheme>:***@",
        detail,
    )


def _render_login(session: Session) -> None:
    st.title("Global Insect Wing Repository")
    st.caption("Version 0.1 · Hymenoptera · right forewing manual digitization")
    st.info(
        "Sign in with an approved account, or request a student account below. "
        "Student signup uses email/password in Version 0.1; administrators "
        "must approve accounts before login."
    )
    if get_settings().auto_bootstrap_demo:
        settings = get_settings()
        if settings.database_url.startswith("sqlite:"):
            st.warning(
                "Hosted demonstration mode uses disposable SQLite storage. Data "
                "can be reset when the app restarts or is redeployed."
            )
        else:
            st.info(
                "Demo bootstrap is enabled for startup provisioning. After the "
                "first successful run, set WBR_AUTO_BOOTSTRAP_DEMO to false."
            )
    sign_in_tab, signup_tab = st.tabs(["Sign in", "Student signup request"])
    with sign_in_tab:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input(
                "Password", type="password", autocomplete="current-password"
            )
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            try:
                normalized_email = normalize_email(email)
            except ValidationError as exc:
                st.error(str(exc))
                return
            user = session.scalar(
                select(User).where(
                    User.email == normalized_email,
                    User.is_active.is_(True),
                )
            )
            if user is None or not verify_password(password, user.password_hash):
                st.error("Email or password is incorrect.")
                return
            st.session_state["wbr_user_id"] = user.id
            st.rerun()

    with signup_tab:
        st.caption(
            "Students may request their own account with a Gmail or institutional "
            "email. The account remains pending until an administrator approves it."
        )
        with st.form("student_signup_form", clear_on_submit=True):
            signup_name = st.text_input("Full name")
            signup_email = st.text_input("Email", autocomplete="email")
            signup_password = st.text_input(
                "Password",
                type="password",
                autocomplete="new-password",
                help="Use at least 12 characters.",
            )
            signup_password_confirm = st.text_input(
                "Confirm password",
                type="password",
                autocomplete="new-password",
            )
            signup_submitted = st.form_submit_button(
                "Request student account",
                type="primary",
            )
        if signup_submitted:
            if signup_password != signup_password_confirm:
                st.error("Passwords do not match.")
                return
            try:
                request_student_signup(
                    session,
                    email=signup_email,
                    full_name=signup_name,
                    password=signup_password,
                )
            except RepositoryError as exc:
                st.error(str(exc))
                return
            st.success(
                "Signup request created. An administrator must approve the "
                "account before you can sign in."
            )


def _active_user(session: Session) -> User | None:
    raw_user_id = st.session_state.get("wbr_user_id")
    if not isinstance(raw_user_id, int):
        return None
    user = session.get(User, raw_user_id)
    if user is None or not user.is_active:
        st.session_state.pop("wbr_user_id", None)
        return None
    return user


def _page_map(role: Role) -> dict[str, PageRenderer]:
    # Imports are delayed until after the schema/login checks so a configuration
    # error can be shown cleanly instead of failing at module import time.
    from wing_repository.ui.analysis_pages import render_published_apis_reference_analysis
    from wing_repository.ui.admin_pages import render_administration
    from wing_repository.ui.repository_pages import (
        render_export,
        render_repository_browser,
    )
    from wing_repository.ui.review_pages import render_expert_review
    from wing_repository.ui.student_pages import (
        render_digitization,
        render_metadata_form,
        render_student_dashboard,
        render_submissions,
        render_upload,
    )

    if role is Role.STUDENT:
        return {
            "Student dashboard": render_student_dashboard,
            "Specimen metadata form": render_metadata_form,
            "Wing-image upload": render_upload,
            "Manual landmark digitization": render_digitization,
            "My submissions": render_submissions,
            "Published Apis Reference Analysis": render_published_apis_reference_analysis,
            "Repository browser": render_repository_browser,
            "TPS and CSV export": render_export,
        }
    if role is Role.EXPERT_REVIEWER:
        return {
            "Expert review": render_expert_review,
            "Published Apis Reference Analysis": render_published_apis_reference_analysis,
            "Repository browser": render_repository_browser,
            "TPS and CSV export": render_export,
        }
    return {
        "Administration": render_administration,
        "Expert review": render_expert_review,
        "Published Apis Reference Analysis": render_published_apis_reference_analysis,
        "Repository browser": render_repository_browser,
        "TPS and CSV export": render_export,
    }


def run() -> None:
    """Render one authenticated application page."""

    st.set_page_config(
        page_title="Global Insect Wing Repository",
        page_icon="🪽",
        layout="wide",
    )
    try:
        schema_ready = ensure_database_ready()
    except Exception as exc:
        logger.exception("Database initialization failed")
        st.error("The configured database could not be initialized.")
        st.code(
            "Check DATABASE_URL and demo bootstrap secrets, then run: "
            "alembic upgrade head"
        )
        st.code(_safe_error_detail(exc))
        st.stop()
    if not schema_ready:
        st.warning("The database schema has not been created yet.")
        st.code("alembic upgrade head\npython scripts/seed_demo.py")
        st.stop()

    with SessionLocal() as session:
        user = _active_user(session)
        if user is None:
            _render_login(session)
            return

        st.sidebar.caption(f"Signed in as {user.full_name}")
        st.sidebar.caption(user.role.value.replace("_", " ").title())
        pages = _page_map(user.role)
        apply_queued_page_navigation(pages, st.session_state)
        if st.session_state.get(CURRENT_PAGE_KEY) not in pages:
            st.session_state[CURRENT_PAGE_KEY] = next(iter(pages))
        selected_page = st.sidebar.radio(
            "Navigation",
            list(pages),
            key=CURRENT_PAGE_KEY,
            label_visibility="collapsed",
        )
        if st.sidebar.button("Sign out", width="stretch"):
            st.session_state.clear()
            st.rerun()

        try:
            pages[selected_page](session, user)
        except RepositoryError as exc:
            session.rollback()
            st.error(str(exc))
        except Exception:
            session.rollback()
            logger.exception("Unhandled error while rendering %s", selected_page)
            st.error("The page could not complete the requested operation.")


__all__ = ["run"]
