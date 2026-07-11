from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from PIL import Image
import pytest

from wing_repository.errors import ConflictError, NotFoundError, StorageError, ValidationError
from wing_repository.image_store import LocalImageStore, inspect_image_bytes


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
