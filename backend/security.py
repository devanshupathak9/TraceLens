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

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)

def hash_password(plain: str) -> str:
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return password_hash.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(user_id: int, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": token_expiry(settings),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        raise credentials_error()


def credentials_error(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def token_expiry(settings: Settings) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None:
        raise credentials_error()

    payload = decode_access_token(credentials.credentials, settings)

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise credentials_error()

    user = await session.get(User, user_id)
    if user is None:
        raise credentials_error()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
