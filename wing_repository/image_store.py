"""Immutable storage and validation for uploaded original images."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
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


class ImageStore(Protocol):
    """Storage interface for immutable original wing-image bytes."""

    def save_original(
        self,
        data: bytes,
        original_filename: str,
        *,
        storage_key: str | None = None,
    ) -> StoredImage:
        """Validate and write one original image without overwriting."""

    def load_original(self, storage_key: str) -> bytes:
        """Read a stored original by its immutable key."""

    def discard_uncommitted(self, storage_key: str) -> None:
        """Compensate for a database failure before persistence is committed."""


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


def _safe_object_key(value: str) -> str:
    """Return a conservative S3/R2 object key or reject unsafe path shapes."""

    if not isinstance(value, str) or not value.strip():
        raise StorageError("Image storage key is missing.")
    if value != value.strip():
        raise StorageError("Image storage key has unsafe surrounding whitespace.")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized.endswith("/"):
        raise StorageError("Image storage key is unsafe.")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise StorageError("Image storage key is unsafe.")
    return normalized


def _safe_key_prefix(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    _safe_object_key(f"{normalized}/placeholder")
    return f"{normalized}/"


def _client_error_code(exc: Exception) -> tuple[str, int | None]:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return "", None
    error = response.get("Error", {})
    metadata = response.get("ResponseMetadata", {})
    code = str(error.get("Code", "")).casefold() if isinstance(error, dict) else ""
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code, status if isinstance(status, int) else None


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


class R2ImageStore:
    """Write-once original-image storage using Cloudflare R2's S3 API."""

    def __init__(
        self,
        *,
        client: Any,
        bucket_name: str,
        key_prefix: str = "originals/",
        max_bytes: int = 25 * 1024 * 1024,
        max_pixels: int = 50_000_000,
    ) -> None:
        if not bucket_name or not bucket_name.strip():
            raise ValueError("WBR_R2_BUCKET_NAME is required for R2 storage.")
        self.client = client
        self.bucket_name = bucket_name
        self.key_prefix = _safe_key_prefix(key_prefix)
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels

    @classmethod
    def from_settings(cls, settings: Settings) -> R2ImageStore:
        """Build the configured Cloudflare R2 store from environment settings."""

        required = {
            "WBR_R2_ENDPOINT_URL": settings.r2_endpoint_url,
            "WBR_R2_BUCKET_NAME": settings.r2_bucket_name,
            "WBR_R2_ACCESS_KEY_ID": settings.r2_access_key_id,
            "WBR_R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "R2 storage requires these environment variables: "
                + ", ".join(missing)
            )
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise StorageError("boto3 is required when WBR_STORAGE_BACKEND=r2.") from exc
        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        return cls(
            client=client,
            bucket_name=settings.r2_bucket_name or "",
            key_prefix=settings.r2_key_prefix,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
        )

    def _generated_key(self, digest: str, extension: str) -> str:
        return _safe_object_key(
            f"{self.key_prefix}{digest[:2]}/{uuid.uuid4().hex}{extension}"
        )

    def save_original(
        self,
        data: bytes,
        original_filename: str,
        *,
        storage_key: str | None = None,
    ) -> StoredImage:
        """Validate and upload bytes without overwriting an existing R2 object."""

        filename = _safe_original_filename(original_filename)
        image_format, mime_type, width, height = inspect_image_bytes(
            data,
            max_bytes=self.max_bytes,
            max_pixels=self.max_pixels,
        )
        digest = sha256(data).hexdigest()
        _mime, extension = _FORMAT_DETAILS[image_format]
        key = (
            self._generated_key(digest, extension)
            if storage_key is None
            else _safe_object_key(storage_key)
        )
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=mime_type,
                IfNoneMatch="*",
                Metadata={
                    "sha256": digest,
                    "original-filename": filename,
                    "image-format": image_format,
                },
            )
        except Exception as exc:
            code, status = _client_error_code(exc)
            if code in {
                "preconditionfailed",
                "conditionalrequestconflict",
            } or status in {409, 412}:
                raise ConflictError(
                    "An image already exists at this immutable storage key."
                ) from exc
            raise StorageError("Could not preserve the uploaded original image in R2.") from exc
        return StoredImage(
            storage_key=key,
            original_filename=filename,
            sha256=digest,
            byte_count=len(data),
            width=width,
            height=height,
            mime_type=mime_type,
            image_format=image_format,
        )

    def load_original(self, storage_key: str) -> bytes:
        """Read stored original bytes from R2."""

        key = _safe_object_key(storage_key)
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            body = response["Body"]
            try:
                return body.read()
            finally:
                close = getattr(body, "close", None)
                if callable(close):
                    close()
        except KeyError as exc:
            raise StorageError("R2 did not return an object body.") from exc
        except Exception as exc:
            code, status = _client_error_code(exc)
            if code in {"nosuchkey", "notfound"} or status == 404:
                raise NotFoundError("Original wing image is missing from R2 storage.") from exc
            raise StorageError("Could not read the original wing image from R2.") from exc

    def discard_uncommitted(self, storage_key: str) -> None:
        """Delete a newly uploaded R2 object after a failed DB transaction."""

        key = _safe_object_key(storage_key)
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
        except Exception as exc:
            raise StorageError("Could not clean up an uncommitted R2 image upload.") from exc


def image_store_from_settings(settings: Settings) -> ImageStore:
    """Build the configured immutable original-image store."""

    if settings.storage_backend == "local":
        return LocalImageStore.from_settings(settings)
    if settings.storage_backend == "r2":
        return R2ImageStore.from_settings(settings)
    raise ValueError("Unsupported WBR_STORAGE_BACKEND.")
