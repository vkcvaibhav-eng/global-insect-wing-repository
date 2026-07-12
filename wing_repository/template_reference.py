"""Reference-guide helpers for human landmark digitization.

Reference images are instructional only. They are never used to generate
coordinates and must not be mixed with the specimen image pixel space.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from wing_repository.models import LandmarkTemplate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ASSET_ROOT = PROJECT_ROOT / "repository_assets"
REFERENCE_GUIDE_ROOT = REFERENCE_ASSET_ROOT / "reference_guides"
LEGACY_ASSET_PREFIX = "demo_data/"


@dataclass(frozen=True, slots=True)
class TemplateReferenceGuide:
    source: str
    caption: str
    citation: str | None = None
    warning: str | None = None


def _template_key(template: LandmarkTemplate) -> tuple[str, int]:
    genus_code = getattr(getattr(template, "taxon", None), "genus_code", "")
    return genus_code.upper(), template.version


def _bundled_reference_guide(template: LandmarkTemplate) -> TemplateReferenceGuide | None:
    if _template_key(template) != ("APIS", 2):
        return None
    return TemplateReferenceGuide(
        source=str(REFERENCE_GUIDE_ROOT / "apis_standard_19_v2_landmark_guide.png"),
        caption=(
            "Apis right forewing 19-landmark guide. Use only as a visual "
            "placement reference; save clicks on the uploaded specimen image."
        ),
        citation=(
            "User-provided teaching guide. Verify licence/source before production "
            "publication or reuse outside this repository."
        ),
        warning=(
            "Guide image is not a specimen record and does not contribute any saved "
            "coordinates."
        ),
    )


def _resolve_reference_source(uri: str) -> str:
    if uri.startswith(("https://", "http://")):
        return uri
    if uri.startswith(LEGACY_ASSET_PREFIX):
        uri = "repository_assets/" + uri.removeprefix(LEGACY_ASSET_PREFIX)
    reference_path = (PROJECT_ROOT / uri).resolve()
    root = PROJECT_ROOT.resolve()
    if reference_path != root and root not in reference_path.parents:
        raise ValueError("Template reference image path must stay inside the repository.")
    return str(reference_path)


def _guide_from_source_json(template: LandmarkTemplate) -> TemplateReferenceGuide | None:
    if not template.source_json:
        return None
    try:
        document: Any = json.loads(template.source_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None
    reference_image = document.get("reference_image")
    if not isinstance(reference_image, dict):
        return None
    uri = reference_image.get("uri")
    if not isinstance(uri, str) or not uri.strip():
        return None
    caption = reference_image.get("caption")
    citation = reference_image.get("citation")
    warning = reference_image.get("warning")
    return TemplateReferenceGuide(
        source=_resolve_reference_source(uri.strip()),
        caption=(
            caption.strip()
            if isinstance(caption, str) and caption.strip()
            else "Template landmark reference guide"
        ),
        citation=(
            citation.strip() if isinstance(citation, str) and citation.strip() else None
        ),
        warning=warning.strip() if isinstance(warning, str) and warning.strip() else None,
    )


def template_reference_guide(
    template: LandmarkTemplate,
) -> TemplateReferenceGuide | None:
    """Return the human guide image for a template, if one is configured."""

    return _guide_from_source_json(template) or _bundled_reference_guide(template)


__all__ = ["TemplateReferenceGuide", "template_reference_guide"]
