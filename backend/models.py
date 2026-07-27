import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base



class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class InferenceStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


_ROLE_ENUM = SAEnum(MessageRole, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])
_STATUS_ENUM = SAEnum(InferenceStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="New chat", server_default="New chat", nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True, order_by="Message.created_at")
    inference_logs: Mapped[list["InferenceLog"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True)
    __table_args__ = (Index("ix_conversations_user_id_last_active_at", "user_id", "last_active_at"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(_ROLE_ENUM, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),)


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Truncated, PII-redacted previews of the call — not the full transcript,
    # which lives in messages. Written by the lambda, never by the backend.
    input_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    output_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InferenceStatus] = mapped_column(_STATUS_ENUM, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="inference_logs")

    __table_args__ = (
        CheckConstraint(
            "total_tokens = prompt_tokens + completion_tokens",
            name="total_tokens_matches_sum",
        ),
    )
