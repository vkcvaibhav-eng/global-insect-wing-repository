from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from wing_repository.models import Annotation
from wing_repository.ui.student_pages import _preferred_annotation_index


def test_preferred_annotation_index_selects_submitted_revision() -> None:
    annotations = cast(
        list[Annotation],
        [
            SimpleNamespace(id=10),
            SimpleNamespace(id=20),
            SimpleNamespace(id=30),
        ],
    )

    assert _preferred_annotation_index(annotations, 20) == 1


def test_preferred_annotation_index_falls_back_to_first_revision() -> None:
    annotations = cast(
        list[Annotation],
        [
            SimpleNamespace(id=10),
            SimpleNamespace(id=20),
        ],
    )

    assert _preferred_annotation_index(annotations, 999) == 0
