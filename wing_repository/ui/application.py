"""Authenticated Streamlit application shell and role-aware navigation."""

from __future__ import annotations

from collections.abc import Callable
import logging

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

PageRenderer = Callable[[Session, User], None]
logger = logging.getLogger(__name__)


def _render_login(session: Session) -> None:
    st.title("Global Insect Wing Repository")
    st.caption("Version 0.1 · Hymenoptera · right forewing manual digitization")
    st.info(
        "Sign in with an account created by the demonstration seed or an "
        "administrator. Credentials are never embedded in the application."
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
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input(
            "Password", type="password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Sign in", type="primary")
    if not submitted:
        return
    try:
        normalized_email = normalize_email(email)
    except ValidationError as exc:
        st.error(str(exc))
        return
    user = session.scalar(
        select(User).where(User.email == normalized_email, User.is_active.is_(True))
    )
    if user is None or not verify_password(password, user.password_hash):
        st.error("Email or password is incorrect.")
        return
    st.session_state["wbr_user_id"] = user.id
    st.rerun()


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
            "Repository browser": render_repository_browser,
            "TPS and CSV export": render_export,
        }
    if role is Role.EXPERT_REVIEWER:
        return {
            "Expert review": render_expert_review,
            "Repository browser": render_repository_browser,
            "TPS and CSV export": render_export,
        }
    return {
        "Administration": render_administration,
        "Expert review": render_expert_review,
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
    except Exception:
        logger.exception("Database initialization failed")
        st.error("The configured database could not be initialized.")
        st.code(
            "Check DATABASE_URL and demo bootstrap secrets, then run: "
            "alembic upgrade head"
        )
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
        if st.session_state.get("wbr_page") not in pages:
            st.session_state["wbr_page"] = next(iter(pages))
        selected_page = st.sidebar.radio(
            "Navigation", list(pages), key="wbr_page", label_visibility="collapsed"
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
