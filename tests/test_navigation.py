from __future__ import annotations

from wing_repository.ui.navigation import (
    CURRENT_PAGE_KEY,
    NEXT_PAGE_KEY,
    apply_queued_page_navigation,
)


def test_apply_queued_page_navigation_updates_current_page() -> None:
    state: dict[str, object] = {
        CURRENT_PAGE_KEY: "My submissions",
        NEXT_PAGE_KEY: "Manual landmark digitization",
    }

    applied = apply_queued_page_navigation(
        {
            "My submissions": object(),
            "Manual landmark digitization": object(),
        },
        state,
    )

    assert applied == "Manual landmark digitization"
    assert state[CURRENT_PAGE_KEY] == "Manual landmark digitization"
    assert NEXT_PAGE_KEY not in state


def test_apply_queued_page_navigation_ignores_invalid_page() -> None:
    state: dict[str, object] = {
        CURRENT_PAGE_KEY: "My submissions",
        NEXT_PAGE_KEY: "Administration",
    }

    applied = apply_queued_page_navigation({"My submissions": object()}, state)

    assert applied is None
    assert state[CURRENT_PAGE_KEY] == "My submissions"
    assert NEXT_PAGE_KEY not in state
