from fastapi import APIRouter, HTTPException, status

from schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from security import CurrentUser, SessionDep, create_access_token
from services.user_service import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    UsernameTaken,
    UserService,
)

user_router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@user_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    try:
        user = await UserService(session).register(payload)
    except EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    except UsernameTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "This username is already taken")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@user_router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    try:
        user = await UserService(session).login(payload.email, payload.password)
    except InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@user_router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    """The user behind the bearer token. The frontend calls this on boot."""
    return UserOut.model_validate(user)


@user_router.post("/logout")
async def logout(user: CurrentUser) -> dict[str, str]:
    """
    JWTs are stateless, so there is nothing to revoke server-side — the client
    forgets the token. The endpoint exists so the frontend has something to call
    and so a token blocklist can slot in later without a contract change.
    """
    return {"status": "ok"}
