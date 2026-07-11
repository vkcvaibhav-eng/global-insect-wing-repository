from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wing_repository.models import Specimen


def test_sqlite_test_database_enforces_foreign_keys(db_session: Session) -> None:
    db_session.add(
        Specimen(
            taxon_id=999_999,
            contributor_id=999_998,
            assignment_id=999_997,
            specimen_code="ORPHAN",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
