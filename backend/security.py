"""Password hashing, JWT issuing/verification, and the current-user dependency."""

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
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Check a password against a stored hash.

    Returns False rather than raising when `hashed` is malformed, so a corrupt
    row can't 500 the login endpoint.
    """
    try:
        return password_hash.verify(plain, hashed)
    except Exception:
        return False


# --- tokens ---------------------------------------------------------------


def create_access_token(user_id: uuid.UUID, settings: Settings | None = None) -> str:
    """
    Issue a signed JWT for this user.

    `sub` is the user id as a string — JWT requires `sub` to be a string, and a
    raw UUID object won't serialise.
    """
    settings = settings or get_settings()
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": token_expiry(settings),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """
    Verify and decode a token.

    Raises `credentials_error()` on any failure — expired, wrong signature,
    malformed. Deliberately doesn't leak which one it was: that distinction is
    useful only to an attacker.
    """
    settings = settings or get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        raise credentials_error()


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

    Raises `credentials_error()` when the header is absent, the token is invalid,
    or the user no longer exists — a token outliving its user must not be treated
    as valid.
    """
    if credentials is None:
        raise credentials_error()

    payload = decode_access_token(credentials.credentials, settings)

    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except ValueError:
        raise credentials_error()

    user = await session.get(User, user_id)
    if user is None:
        raise credentials_error()

    return user


# Aliases so route signatures stay short: `user: CurrentUser`.
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
