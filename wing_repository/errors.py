"""Domain-specific exceptions raised by the repository application.

The Streamlit layer can catch these exceptions and present concise messages
without depending on SQLAlchemy or storage implementation details.
"""

from __future__ import annotations


class RepositoryError(Exception):
    """Base class for expected application/domain failures."""


class ValidationError(RepositoryError):
    """Input data is malformed or violates a domain invariant."""


class AuthenticationError(RepositoryError):
    """Credentials are invalid or an account cannot authenticate."""


class AuthorizationError(RepositoryError):
    """The authenticated actor is not allowed to perform an operation."""


class NotFoundError(RepositoryError):
    """A requested domain entity does not exist or is not visible to the actor."""


class ConflictError(RepositoryError):
    """The operation conflicts with existing persistent state."""


class InvalidStateError(ConflictError):
    """A workflow transition is invalid for the entity's current state."""


class IncompleteAnnotationError(ValidationError):
    """An annotation does not contain its template's exact landmark set."""


class TemplateVersionMismatchError(ValidationError):
    """Data from different landmark-template identities would be combined."""


class StorageError(RepositoryError):
    """An original image could not be validated, stored, or read safely."""


class ExportError(RepositoryError):
    """Approved records cannot be serialized under the requested constraints."""
