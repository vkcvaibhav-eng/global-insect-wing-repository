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


class SpeciesIdentificationMethod(StringEnum):
    MOLECULAR = "molecular"
    TAXONOMIST = "taxonomist"
    DICHOTOMOUS_KEY = "dichotomous_key"


class AnnotationStatus(StringEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"
    DELETED = "deleted"
    RETURNED = "returned"
    APPROVED = "approved"


class ReviewDecision(StringEnum):
    APPROVE = "approve"
    RETURN = "return"


class AnalysisType(StringEnum):
    APIS_MELLIFERA_EU_REGION = "apis_mellifera_eu_region"
    APIS_MELLIFERA_LINEAGE = "apis_mellifera_lineage"
    APIS_MELLIFERA_NEAREST_SHAPE = "apis_mellifera_nearest_shape"


class AnalysisModelStatus(StringEnum):
    BUILDING = "building"
    VALIDATION_FAILED = "validation_failed"
    VALIDATED = "validated"
    ACTIVE = "active"
    RETIRED = "retired"


class AnalysisRunStatus(StringEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisQualityStatus(StringEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class AnalysisOutlierStatus(StringEnum):
    IN_DISTRIBUTION = "in_distribution"
    OUTSIDE_REFERENCE_DISTRIBUTION = "outside_reference_distribution"
