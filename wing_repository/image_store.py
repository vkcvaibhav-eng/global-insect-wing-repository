"""Immutable local storage and validation for uploaded original images."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
import uuid
import warnings

from PIL import Image, UnidentifiedImageError

from .errors import ConflictError, NotFoundError, StorageError, ValidationError

if TYPE_CHECKING:
    from .config import Settings

_FORMAT_DETAILS: dict[str, tuple[str, str]] = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
}


@dataclass(frozen=True, slots=True)
class StoredImage:
    """Metadata produced while preserving one immutable original upload."""

    storage_key: str
    original_filename: str
    sha256: str
    byte_count: int
    width: int
    height: int
    mime_type: str
    image_format: str


def _safe_original_filename(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Original filename must be text.")
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        raise ValidationError("Original filename is missing.")
    return name[:255]


def inspect_image_bytes(
    data: bytes,
    *,
    max_bytes: int = 25 * 1024 * 1024,
    max_pixels: int = 50_000_000,
) -> tuple[str, str, int, int]:
    """Validate PNG/JPEG bytes and return format, MIME type, width, height."""

    if not isinstance(data, bytes):
        raise ValidationError("Uploaded image content must be bytes.")
    if not data:
        raise ValidationError("Uploaded image is empty.")
    if len(data) > max_bytes:
        raise ValidationError(f"Uploaded image exceeds the {max_bytes}-byte limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
                if image_format not in _FORMAT_DETAILS:
                    raise ValidationError("Only PNG and JPEG wing images are supported.")
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ValidationError("Uploaded image dimensions are outside allowed limits.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("Animated or multi-frame images are not supported.")
                image.verify()
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError("Uploaded image is too large to decode safely.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Uploaded content is not a valid PNG or JPEG image.") from exc
    mime_type, _extension = _FORMAT_DETAILS[image_format]
    return image_format, mime_type, width, height


class LocalImageStore:
    """Write-once storage rooted at one configured local directory."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_bytes: int = 25 * 1024 * 1024,
        max_pixels: int = 50_000_000,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels

    @classmethod
    def from_settings(cls, settings: Settings) -> LocalImageStore:
        """Build the configured store under ``data_dir/originals``."""

        return cls(
            settings.original_image_dir,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
        )

    def _resolve_key(self, storage_key: str) -> Path:
        if not isinstance(storage_key, str) or not storage_key.strip():
            raise StorageError("Image storage key is missing.")
        key_path = Path(storage_key)
        if key_path.is_absolute() or ".." in key_path.parts:
            raise StorageError("Image storage key is unsafe.")
        candidate = (self.root / key_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Image storage key escapes the storage root.") from exc
        return candidate

    def save_original(
        self,
        data: bytes,
        original_filename: str,
        *,
        storage_key: str | None = None,
    ) -> StoredImage:
        """Validate and save bytes without ever overwriting an existing object."""

        filename = _safe_original_filename(original_filename)
        image_format, mime_type, width, height = inspect_image_bytes(
            data,
            max_bytes=self.max_bytes,
            max_pixels=self.max_pixels,
        )
        digest = sha256(data).hexdigest()
        _mime, extension = _FORMAT_DETAILS[image_format]
        key = (
            f"{digest[:2]}/{uuid.uuid4().hex}{extension}"
            if storage_key is None
            else storage_key
        )
        path = self._resolve_key(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as destination:
                destination.write(data)
        except FileExistsError as exc:
            raise ConflictError("An image already exists at this immutable storage key.") from exc
        except OSError as exc:
            raise StorageError("Could not preserve the uploaded original image.") from exc
        return StoredImage(
            storage_key=key.replace("\\", "/"),
            original_filename=filename,
            sha256=digest,
            byte_count=len(data),
            width=width,
            height=height,
            mime_type=mime_type,
            image_format=image_format,
        )

    def load_original(self, storage_key: str) -> bytes:
        """Read a stored original by its relative, validated key."""

        path = self._resolve_key(storage_key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise NotFoundError("Original wing image is missing from storage.") from exc
        except OSError as exc:
            raise StorageError("Could not read the original wing image.") from exc

    def absolute_path(self, storage_key: str) -> Path:
        """Return a safe resolved path for display/streaming integrations."""

        path = self._resolve_key(storage_key)
        if not path.is_file():
            raise NotFoundError("Original wing image is missing from storage.")
        return path

    def discard_uncommitted(self, storage_key: str) -> None:
        """Remove a newly written object whose database transaction failed.

        This method is intentionally for compensation before an image becomes a
        scientific record.  Application code must never call it for a persisted
        ``WingImage``.
        """

        path = self._resolve_key(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Could not clean up an uncommitted image upload.") from exc
