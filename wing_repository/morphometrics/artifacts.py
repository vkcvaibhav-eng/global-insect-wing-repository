"""Versioned model artifact persistence and checksum validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wing_repository.errors import StorageError, ValidationError

if TYPE_CHECKING:
    from wing_repository.config import Settings


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """A saved model artifact with its storage key and checksum."""

    storage_key: str
    sha256: str
    byte_size: int


def artifact_path(root: Path, storage_key: str) -> Path:
    """Resolve a relative artifact storage key under a configured root."""

    if Path(storage_key).is_absolute() or ".." in Path(storage_key).parts:
        raise ValidationError("Artifact storage key must be a safe relative path.")
    return root / storage_key


def _safe_object_key(value: str) -> str:
    """Return a conservative S3/R2 object key or reject unsafe path shapes."""

    if not isinstance(value, str) or not value.strip():
        raise StorageError("Artifact storage key is missing.")
    if value != value.strip():
        raise StorageError("Artifact storage key has unsafe surrounding whitespace.")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized.endswith("/"):
        raise StorageError("Artifact storage key is unsafe.")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise StorageError("Artifact storage key is unsafe.")
    return normalized


def _safe_key_prefix(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    _safe_object_key(f"{normalized}/placeholder")
    return f"{normalized}/"


def r2_artifact_key(*, prefix: str | None, storage_key: str) -> str:
    """Resolve a model storage key to its object-store key."""

    return _safe_object_key(f"{_safe_key_prefix(prefix)}{_safe_object_key(storage_key)}")


def _client_error_code(exc: Exception) -> tuple[str, int | None]:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return "", None
    error = response.get("Error", {})
    metadata = response.get("ResponseMetadata", {})
    code = str(error.get("Code", "")).casefold() if isinstance(error, dict) else ""
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code, status if isinstance(status, int) else None


def _r2_client_from_settings(settings: Settings) -> Any:
    required = {
        "WBR_R2_ENDPOINT_URL": settings.r2_endpoint_url,
        "WBR_R2_BUCKET_NAME": settings.r2_bucket_name,
        "WBR_R2_ACCESS_KEY_ID": settings.r2_access_key_id,
        "WBR_R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise StorageError(
            "R2 analysis artifacts require these environment variables: "
            + ", ".join(missing)
        )
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise StorageError("boto3 is required when WBR_ANALYSIS_ARTIFACT_BACKEND=r2.") from exc
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def save_pickle_artifact(
    payload: dict[str, Any],
    *,
    root: Path,
    storage_key: str,
) -> StoredArtifact:
    """Save a deterministic pickle artifact without overwriting active versions."""

    path = artifact_path(root, storage_key)
    if path.exists():
        raise ValidationError("Model artifact already exists and will not be overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    path.write_bytes(data)
    return StoredArtifact(
        storage_key=storage_key,
        sha256=sha256(data).hexdigest(),
        byte_size=len(data),
    )


def save_r2_pickle_artifact(
    payload: dict[str, Any],
    *,
    client: Any,
    bucket_name: str,
    key_prefix: str | None,
    storage_key: str,
) -> StoredArtifact:
    """Save a pickle artifact to R2 without overwriting active versions."""

    if not bucket_name or not bucket_name.strip():
        raise StorageError("WBR_R2_BUCKET_NAME is required for R2 artifact storage.")
    key = r2_artifact_key(prefix=key_prefix, storage_key=storage_key)
    try:
        client.head_object(Bucket=bucket_name, Key=key)
    except Exception as exc:
        code, status = _client_error_code(exc)
        if code not in {"404", "nosuchkey", "notfound"} and status != 404:
            raise StorageError("Could not check whether the model artifact exists in R2.") from exc
    else:
        raise ValidationError("Model artifact already exists and will not be overwritten.")

    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    digest = sha256(data).hexdigest()
    try:
        client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=data,
            ContentType="application/octet-stream",
            IfNoneMatch="*",
            Metadata={"sha256": digest, "storage-key": storage_key},
        )
    except Exception as exc:
        code, status = _client_error_code(exc)
        if code in {"preconditionfailed", "conditionalrequestconflict"} or status in {409, 412}:
            raise ValidationError("Model artifact already exists and will not be overwritten.") from exc
        raise StorageError("Could not save the model artifact in R2.") from exc
    return StoredArtifact(storage_key=storage_key, sha256=digest, byte_size=len(data))


def load_pickle_artifact(
    *,
    root: Path,
    storage_key: str,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load and verify a saved model artifact."""

    data = artifact_path(root, storage_key).read_bytes()
    digest = sha256(data).hexdigest()
    if digest != expected_sha256:
        raise ValidationError("Model artifact checksum validation failed.")
    payload = pickle.loads(data)
    if not isinstance(payload, dict):
        raise ValidationError("Model artifact payload is invalid.")
    return payload


def load_r2_pickle_artifact(
    *,
    client: Any,
    bucket_name: str,
    key_prefix: str | None,
    storage_key: str,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load and verify a saved model artifact from R2."""

    if not bucket_name or not bucket_name.strip():
        raise StorageError("WBR_R2_BUCKET_NAME is required for R2 artifact storage.")
    key = r2_artifact_key(prefix=key_prefix, storage_key=storage_key)
    try:
        response = client.get_object(Bucket=bucket_name, Key=key)
        body = response["Body"]
        try:
            data = body.read()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
    except KeyError as exc:
        raise StorageError("R2 did not return a model artifact body.") from exc
    except Exception as exc:
        code, status = _client_error_code(exc)
        if code in {"nosuchkey", "notfound"} or status == 404:
            raise StorageError("Model artifact is missing from R2 storage.") from exc
        raise StorageError("Could not read the model artifact from R2.") from exc

    digest = sha256(data).hexdigest()
    if digest != expected_sha256:
        raise ValidationError("Model artifact checksum validation failed.")
    try:
        payload = pickle.loads(data)
    except Exception as exc:
        raise ValidationError("Model artifact payload is invalid.") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Model artifact payload is invalid.")
    return payload


def save_configured_pickle_artifact(
    payload: dict[str, Any],
    *,
    settings: Settings,
    storage_key: str,
    local_root: Path | None = None,
) -> StoredArtifact:
    """Save an analysis artifact using the configured local or R2 backend."""

    if settings.analysis_artifact_backend == "local":
        return save_pickle_artifact(
            payload,
            root=local_root or settings.analysis_artifact_dir,
            storage_key=storage_key,
        )
    if settings.analysis_artifact_backend == "r2":
        return save_r2_pickle_artifact(
            payload,
            client=_r2_client_from_settings(settings),
            bucket_name=settings.r2_bucket_name or "",
            key_prefix=settings.analysis_artifact_r2_prefix,
            storage_key=storage_key,
        )
    raise StorageError("Unsupported WBR_ANALYSIS_ARTIFACT_BACKEND.")


def load_configured_pickle_artifact(
    *,
    settings: Settings,
    storage_key: str,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load an analysis artifact using the configured local or R2 backend."""

    if settings.analysis_artifact_backend == "local":
        return load_pickle_artifact(
            root=settings.analysis_artifact_dir,
            storage_key=storage_key,
            expected_sha256=expected_sha256,
        )
    if settings.analysis_artifact_backend == "r2":
        return load_r2_pickle_artifact(
            client=_r2_client_from_settings(settings),
            bucket_name=settings.r2_bucket_name or "",
            key_prefix=settings.analysis_artifact_r2_prefix,
            storage_key=storage_key,
            expected_sha256=expected_sha256,
        )
    raise StorageError("Unsupported WBR_ANALYSIS_ARTIFACT_BACKEND.")


__all__ = [
    "StoredArtifact",
    "artifact_path",
    "load_configured_pickle_artifact",
    "load_pickle_artifact",
    "load_r2_pickle_artifact",
    "r2_artifact_key",
    "save_configured_pickle_artifact",
    "save_pickle_artifact",
    "save_r2_pickle_artifact",
]
