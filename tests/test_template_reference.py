from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from wing_repository.models import LandmarkTemplate
from wing_repository.template_reference import template_reference_guide


def test_bundled_apis_v2_reference_guide_exists() -> None:
    template = cast(
        LandmarkTemplate,
        SimpleNamespace(
            version=2,
            source_json=None,
            taxon=SimpleNamespace(genus_code="APIS"),
        ),
    )

    guide = template_reference_guide(template)

    assert guide is not None
    assert Path(guide.source).exists()
    assert "19-landmark guide" in guide.caption


def test_reference_guide_can_be_read_from_template_source_json() -> None:
    template = cast(
        LandmarkTemplate,
        SimpleNamespace(
            version=99,
            source_json=json.dumps(
                {
                    "reference_image": {
                        "uri": "demo_data/reference_guides/apis_standard_19_v2_landmark_guide.png",
                        "caption": "Custom guide",
                        "citation": "Custom citation",
                    }
                }
            ),
            taxon=SimpleNamespace(genus_code="TEST"),
        ),
    )

    guide = template_reference_guide(template)

    assert guide is not None
    assert Path(guide.source).exists()
    assert guide.caption == "Custom guide"
    assert guide.citation == "Custom citation"


def test_reference_guide_missing_when_not_configured() -> None:
    template = cast(
        LandmarkTemplate,
        SimpleNamespace(
            version=1,
            source_json=None,
            taxon=SimpleNamespace(genus_code="TEST"),
        ),
    )

    assert template_reference_guide(template) is None
