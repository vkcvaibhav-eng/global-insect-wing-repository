from __future__ import annotations

from io import BytesIO

import pytest

from wing_repository.errors import ValidationError
from wing_repository.morphometrics.artifacts import (
    load_r2_pickle_artifact,
    r2_artifact_key,
    save_r2_pickle_artifact,
)


class FakeR2ClientError(Exception):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        }


class FakeR2ArtifactClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_object(self, **kwargs: object) -> dict[str, int]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        try:
            data = self.objects[(bucket, key)]
        except KeyError as exc:
            raise FakeR2ClientError("404", 404) from exc
        return {"ContentLength": len(data)}

    def put_object(self, **kwargs: object) -> None:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        object_key = (bucket, key)
        if kwargs.get("IfNoneMatch") == "*" and object_key in self.objects:
            raise FakeR2ClientError("PreconditionFailed", 412)
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[object_key] = body

    def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        try:
            data = self.objects[(bucket, key)]
        except KeyError as exc:
            raise FakeR2ClientError("NoSuchKey", 404) from exc
        return {"Body": BytesIO(data)}


def test_r2_artifact_key_uses_analysis_prefix() -> None:
    assert (
        r2_artifact_key(
            prefix="analysis-artifacts/",
            storage_key="apis_reference/v1/model.pkl",
        )
        == "analysis-artifacts/apis_reference/v1/model.pkl"
    )


def test_r2_pickle_artifact_round_trip_and_checksum_validation() -> None:
    client = FakeR2ArtifactClient()
    payload = {"reference_wings": 84_426, "model_version": 1}

    stored = save_r2_pickle_artifact(
        payload,
        client=client,
        bucket_name="wing-originals",
        key_prefix="analysis-artifacts/",
        storage_key="apis_reference/v1/model.pkl",
    )

    assert stored.storage_key == "apis_reference/v1/model.pkl"
    assert ("wing-originals", "analysis-artifacts/apis_reference/v1/model.pkl") in client.objects
    assert (
        load_r2_pickle_artifact(
            client=client,
            bucket_name="wing-originals",
            key_prefix="analysis-artifacts/",
            storage_key=stored.storage_key,
            expected_sha256=stored.sha256,
        )
        == payload
    )
    with pytest.raises(ValidationError, match="checksum"):
        load_r2_pickle_artifact(
            client=client,
            bucket_name="wing-originals",
            key_prefix="analysis-artifacts/",
            storage_key=stored.storage_key,
            expected_sha256="not-the-real-checksum",
        )
    with pytest.raises(ValidationError, match="already exists"):
        save_r2_pickle_artifact(
            payload,
            client=client,
            bucket_name="wing-originals",
            key_prefix="analysis-artifacts/",
            storage_key=stored.storage_key,
        )
