"""
Pydantic request and response models — all request validation lives here.

These are the API contract: the README documents them, and the frontend must
read exactly these field names.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models import MessageRole

Password = Annotated[str, Field(min_length=8, max_length=128)]
Name = Annotated[str, Field(min_length=1, max_length=100)]
Title = Annotated[str, Field(min_length=1, max_length=200)]


class ORMModel(BaseModel):
    """Base for responses built directly from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


# --- users ----------------------------------------------------------------


class RegisterRequest(BaseModel):
    name: Name
    email: EmailStr
    password: Password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: int
    name: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# --- conversations --------------------------------------------------------


class ConversationCreate(BaseModel):
    """Both optional: title defaults to "New chat" (renamed by the first
    message), model defaults to the server's configured default."""

    title: Title | None = None
    model: str | None = None


class ConversationUpdate(BaseModel):
    """PATCH semantics — only the fields present are changed."""

    title: Title | None = None


class ConversationSummary(ORMModel):
    """Sidebar row. `message_count` is computed, not a column."""

    id: int
    title: str
    model: str
    created_at: datetime
    last_active_at: datetime
    message_count: int = 0


class MessageOut(ORMModel):
    id: int
    conversation_id: int
    role: MessageRole
    content: str
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut] = []


# --- messages (chat) ------------------------------------------------------


class MessageCreate(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=32_000)]


class SendMessageResponse(BaseModel):
    """One chat turn: the stored user message and the assistant's reply."""

    user_message: MessageOut
    assistant_message: MessageOut
