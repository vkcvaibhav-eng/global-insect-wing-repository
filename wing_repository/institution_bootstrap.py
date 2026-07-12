"""Institution bootstrap for the first real repository administrator."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.config import Settings
from wing_repository.enums import Role
from wing_repository.errors import ConflictError, ValidationError
from wing_repository.models import User
from wing_repository.security import hash_password, normalize_email
from wing_repository.services import (
    MIN_ACCOUNT_PASSWORD_CHARACTERS,
    import_bundled_standard_template,
)


LEGACY_EXAMPLE_EMAILS = {
    "admin@example.test",
    "student@example.test",
    "reviewer@example.test",
}


def institution_bootstrap_is_configured(settings: Settings) -> bool:
    """Return whether startup has enough intent to create a real administrator."""

    return bool(settings.bootstrap_admin_email and settings.bootstrap_admin_email.strip())


def _validated_bootstrap_password(settings: Settings) -> str:
    password = settings.bootstrap_admin_password
    if not password:
        raise ConflictError("WBR_BOOTSTRAP_ADMIN_PASSWORD is required for first-admin bootstrap.")
    if len(password) < MIN_ACCOUNT_PASSWORD_CHARACTERS:
        raise ValidationError(
            f"WBR_BOOTSTRAP_ADMIN_PASSWORD must be at least "
            f"{MIN_ACCOUNT_PASSWORD_CHARACTERS} characters."
        )
    return password


def _bootstrap_full_name(settings: Settings) -> str:
    full_name = (settings.bootstrap_admin_full_name or "").strip()
    return full_name or "Repository Administrator"


def _deactivate_legacy_example_accounts(session: Session, *, admin_email: str) -> int:
    legacy_emails = LEGACY_EXAMPLE_EMAILS - {admin_email}
    if not legacy_emails:
        return 0
    accounts = list(
        session.scalars(
            select(User).where(
                User.email.in_(legacy_emails),
                User.is_active.is_(True),
            )
        )
    )
    for account in accounts:
        account.is_active = False
    return len(accounts)


def ensure_institution_bootstrap(
    session: Session,
    settings: Settings,
) -> dict[str, str]:
    """Create/update the configured real admin and standard Apis template."""

    if not institution_bootstrap_is_configured(settings):
        return {}

    admin_email = normalize_email(settings.bootstrap_admin_email or "")
    admin = session.scalar(select(User).where(User.email == admin_email))
    if admin is None:
        admin = User(
            email=admin_email,
            full_name=_bootstrap_full_name(settings),
            password_hash=hash_password(_validated_bootstrap_password(settings)),
            role=Role.ADMINISTRATOR,
            is_active=True,
        )
        session.add(admin)
        session.flush()
        admin_state = "created"
    else:
        if admin.role is not Role.ADMINISTRATOR:
            raise ConflictError(
                f"WBR_BOOTSTRAP_ADMIN_EMAIL belongs to a {admin.role.value} account, "
                "not an administrator."
            )
        admin_state_parts: list[str] = []
        if not admin.is_active:
            admin.is_active = True
            admin_state_parts.append("reactivated")
        if settings.bootstrap_admin_full_name and admin.full_name != _bootstrap_full_name(settings):
            admin.full_name = _bootstrap_full_name(settings)
            admin_state_parts.append("name updated")
        if settings.bootstrap_admin_reset_password:
            admin.password_hash = hash_password(_validated_bootstrap_password(settings))
            admin_state_parts.append("password reset")
        admin_state = "; ".join(admin_state_parts) or "existing"

    template = import_bundled_standard_template(session, admin)
    disabled_count = _deactivate_legacy_example_accounts(session, admin_email=admin_email)
    session.commit()
    return {
        "administrator": f"{admin_state} ({admin.email})",
        "template": f"available (ID {template.id}, version {template.version})",
        "legacy_example_accounts_disabled": str(disabled_count),
    }


__all__ = [
    "ensure_institution_bootstrap",
    "institution_bootstrap_is_configured",
]
