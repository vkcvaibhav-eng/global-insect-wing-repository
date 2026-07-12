"""Safe Streamlit page navigation helpers."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

import streamlit as st


CURRENT_PAGE_KEY = "wbr_page"
NEXT_PAGE_KEY = "wbr_next_page"


def apply_queued_page_navigation(
    pages: Mapping[str, Any],
    state: MutableMapping[str, Any],
) -> str | None:
    """Apply a queued page change before the navigation widget is rendered."""

    requested_page = state.pop(NEXT_PAGE_KEY, None)
    if isinstance(requested_page, str) and requested_page in pages:
        state[CURRENT_PAGE_KEY] = requested_page
        return requested_page
    return None


def move_to_page(page_name: str) -> None:
    """Queue another role-visible page, then rerun safely."""

    st.session_state[NEXT_PAGE_KEY] = page_name
    st.rerun()
