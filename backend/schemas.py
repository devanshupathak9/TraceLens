from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from models import MessageRole

Password = Annotated[str, Field(min_length=8, max_length=128)]
Name = Annotated[str, Field(min_length=1, max_length=100)]
Title = Annotated[str, Field(min_length=1, max_length=200)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class ConversationCreate(BaseModel):
    title: Title | None = None
    model: str | None = None


class ConversationUpdate(BaseModel):
    title: Title | None = None


class ConversationSummary(ORMModel):
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


class ModelUsage(BaseModel):
    model: str
    calls: int
    avg_latency_ms: int
    prompt_tokens: int
    completion_tokens: int


class DashboardStats(BaseModel):
    total_calls: int
    success_calls: int
    failed_calls: int
    avg_latency_ms: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    models: list[ModelUsage]


class MessageCreate(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=32_000)]


class SendMessageResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
