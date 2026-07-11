from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from PIL import Image
import pytest

from wing_repository.errors import ConflictError, NotFoundError, StorageError, ValidationError
from wing_repository.image_store import LocalImageStore, R2ImageStore, inspect_image_bytes


class FakeR2ClientError(Exception):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        }


class FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.put_calls = 0

    def put_object(self, **kwargs: object) -> None:
        self.put_calls += 1
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        object_key = (bucket, key)
        if kwargs.get("IfNoneMatch") == "*" and object_key in self.objects:
            raise FakeR2ClientError("PreconditionFailed", 412)
        self.objects[object_key] = dict(kwargs)

    def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        try:
            body = self.objects[(bucket, key)]["Body"]
        except KeyError as exc:
            raise FakeR2ClientError("NoSuchKey", 404) from exc
        assert isinstance(body, bytes)
        return {"Body": BytesIO(body)}

    def delete_object(self, **kwargs: object) -> None:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        self.objects.pop((bucket, key), None)


def _png_bytes(*, width: int = 12, height: int = 8) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def test_save_original_preserves_exact_bytes_and_metadata(tmp_path) -> None:
    data = _png_bytes(width=12, height=8)
    store = LocalImageStore(tmp_path)

    saved = store.save_original(
        data,
        "C:\\private\\student-wing.png",
        storage_key="originals/specimen-1.png",
    )

    assert saved.storage_key == "originals/specimen-1.png"
    assert saved.original_filename == "student-wing.png"
    assert saved.sha256 == sha256(data).hexdigest()
    assert saved.byte_count == len(data)
    assert (saved.width, saved.height) == (12, 8)
    assert saved.mime_type == "image/png"
    assert saved.image_format == "PNG"
    assert store.load_original(saved.storage_key) == data
    assert store.absolute_path(saved.storage_key).read_bytes() == data


def test_save_original_never_overwrites_existing_key(tmp_path) -> None:
    first = _png_bytes(width=12, height=8)
    second = _png_bytes(width=7, height=5)
    store = LocalImageStore(tmp_path)
    key = "originals/fixed.png"
    store.save_original(first, "first.png", storage_key=key)

    with pytest.raises(ConflictError):
        store.save_original(second, "second.png", storage_key=key)

    assert store.load_original(key) == first


@pytest.mark.parametrize("key", ["../escape.png", "/absolute.png", "", "   "])
def test_storage_keys_cannot_escape_storage_root(tmp_path, key: str) -> None:
    store = LocalImageStore(tmp_path)

    with pytest.raises(StorageError):
        store.save_original(_png_bytes(), "wing.png", storage_key=key)


@pytest.mark.parametrize("data", [b"", b"not an image"])
def test_invalid_upload_is_rejected_without_creating_a_file(tmp_path, data: bytes) -> None:
    store = LocalImageStore(tmp_path)

    with pytest.raises(ValidationError):
        store.save_original(data, "wing.png")

    assert list(tmp_path.rglob("*")) == []


def test_upload_limits_are_enforced() -> None:
    data = _png_bytes(width=12, height=8)

    with pytest.raises(ValidationError, match="byte limit"):
        inspect_image_bytes(data, max_bytes=len(data) - 1)
    with pytest.raises(ValidationError, match="dimensions"):
        inspect_image_bytes(data, max_pixels=95)


def test_discard_uncommitted_removes_only_requested_new_object(tmp_path) -> None:
    store = LocalImageStore(tmp_path)
    saved = store.save_original(_png_bytes(), "wing.png")

    store.discard_uncommitted(saved.storage_key)

    with pytest.raises(NotFoundError):
        store.load_original(saved.storage_key)


def test_r2_save_original_preserves_exact_bytes_and_metadata() -> None:
    data = _png_bytes(width=20, height=11)
    client = FakeR2Client()
    store = R2ImageStore(client=client, bucket_name="wing-bucket")

    saved = store.save_original(
        data,
        "C:\\private\\student-wing.png",
        storage_key="originals/specimen-1.png",
    )

    assert saved.storage_key == "originals/specimen-1.png"
    assert saved.original_filename == "student-wing.png"
    assert saved.sha256 == sha256(data).hexdigest()
    assert saved.byte_count == len(data)
    assert (saved.width, saved.height) == (20, 11)
    assert saved.mime_type == "image/png"
    assert saved.image_format == "PNG"
    assert store.load_original(saved.storage_key) == data
    stored_object = client.objects[("wing-bucket", "originals/specimen-1.png")]
    assert stored_object["Body"] == data
    assert stored_object["ContentType"] == "image/png"
    assert stored_object["IfNoneMatch"] == "*"


def test_r2_generated_keys_use_the_configured_prefix() -> None:
    client = FakeR2Client()
    store = R2ImageStore(
        client=client,
        bucket_name="wing-bucket",
        key_prefix="hymenoptera/originals/",
    )

    saved = store.save_original(_png_bytes(), "wing.png")

    assert saved.storage_key.startswith("hymenoptera/originals/")
    assert ("wing-bucket", saved.storage_key) in client.objects


def test_r2_save_original_never_overwrites_existing_key() -> None:
    first = _png_bytes(width=12, height=8)
    second = _png_bytes(width=7, height=5)
    store = R2ImageStore(client=FakeR2Client(), bucket_name="wing-bucket")
    key = "originals/fixed.png"
    store.save_original(first, "first.png", storage_key=key)

    with pytest.raises(ConflictError):
        store.save_original(second, "second.png", storage_key=key)

    assert store.load_original(key) == first


@pytest.mark.parametrize("key", ["../escape.png", "/absolute.png", "", "   "])
def test_r2_storage_keys_reject_unsafe_shapes(key: str) -> None:
    store = R2ImageStore(client=FakeR2Client(), bucket_name="wing-bucket")

    with pytest.raises(StorageError):
        store.save_original(_png_bytes(), "wing.png", storage_key=key)


def test_r2_invalid_upload_is_rejected_before_client_call() -> None:
    client = FakeR2Client()
    store = R2ImageStore(client=client, bucket_name="wing-bucket")

    with pytest.raises(ValidationError):
        store.save_original(b"not an image", "wing.png")

    assert client.put_calls == 0
    assert client.objects == {}


def test_r2_discard_uncommitted_removes_uploaded_object() -> None:
    client = FakeR2Client()
    store = R2ImageStore(client=client, bucket_name="wing-bucket")
    saved = store.save_original(_png_bytes(), "wing.png")

    store.discard_uncommitted(saved.storage_key)

    with pytest.raises(NotFoundError):
        store.load_original(saved.storage_key)
