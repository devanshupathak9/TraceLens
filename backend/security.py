"""
Password hashing, JWT issuing/verification, and the current-user dependency.

Structure only — bodies raise NotImplementedError.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from database import get_session
from models import User

# Argon2id by default. pwdlib replaces passlib, which is unmaintained and emits a
# spurious version warning against bcrypt 4.x.
password_hash = PasswordHash.recommended()

# auto_error=False so a missing header reaches our own handler and returns the
# `{"detail": ...}` shape the frontend parses, rather than FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False)


# --- passwords ------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage."""
    raise NotImplementedError


def verify_password(plain: str, hashed: str) -> bool:
    """
    Check a password against a stored hash.

    Must return False rather than raising when `hashed` is malformed, so a
    corrupt row can't 500 the login endpoint.
    """
    raise NotImplementedError


# --- tokens ---------------------------------------------------------------


def create_access_token(user_id: uuid.UUID, settings: Settings | None = None) -> str:
    """
    Issue a signed JWT for this user.

    Claims to include: `sub` (the user id as a string — JWT requires `sub` to be
    a string, and a raw UUID object won't serialise), `exp`, and `iat`.
    """
    raise NotImplementedError


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """
    Verify and decode a token.

    Raise `credentials_error()` on any failure — expired, wrong signature,
    malformed. Do not leak which one it was: that distinction is useful only to
    an attacker.
    """
    raise NotImplementedError


def credentials_error(detail: str = "Could not validate credentials") -> HTTPException:
    """
    401 with the WWW-Authenticate header.

    The frontend's api/client.ts treats any 401 as session expiry and drops the
    user to the sign-in screen.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def token_expiry(settings: Settings) -> datetime:
    """Absolute expiry for a newly issued token. UTC-aware, never naive."""
    return datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)


# --- dependencies ---------------------------------------------------------


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """
    Resolve the bearer token to a User row.

    Raise `credentials_error()` when the header is absent, the token is invalid,
    or the user no longer exists — a token outliving its user must not be treated
    as valid.
    """
    raise NotImplementedError


# Aliases so route signatures stay short: `user: CurrentUser`.
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
