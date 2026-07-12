"""Closed vocabularies persisted by the version 0.1 schema."""

from __future__ import annotations

from enum import Enum


class StringEnum(str, Enum):
    """A string-valued enum with useful Streamlit display behaviour."""

    def __str__(self) -> str:
        return self.value


class Role(StringEnum):
    ADMINISTRATOR = "administrator"
    STUDENT = "student"
    EXPERT_REVIEWER = "expert_reviewer"


class WingSide(StringEnum):
    RIGHT = "right"


class WingType(StringEnum):
    FOREWING = "forewing"


class TemplateStatus(StringEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class AnnotationStatus(StringEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"
    RETURNED = "returned"
    APPROVED = "approved"


class ReviewDecision(StringEnum):
    APPROVE = "approve"
    RETURN = "return"
