import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class InferenceStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


# VARCHAR + CHECK instead of native Postgres enums — easier migrations.
_ROLE_ENUM = SAEnum(MessageRole, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])
_STATUS_ENUM = SAEnum(InferenceStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
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
    # Bumped by the chat service on every new message — the sidebar sort key.
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True, order_by="Message.created_at")
    inference_logs: Mapped[list["InferenceLog"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True)

    # The sidebar query: this user's conversations, most recent first.
    __table_args__ = (Index("ix_conversations_user_id_last_active_at", "user_id", "last_active_at"),)


class Message(Base):
    """Transcript only — call metadata lives in inference_logs."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(_ROLE_ENUM, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    # Loading a transcript in order, and building the context window.
    __table_args__ = (Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),)


class InferenceLog(Base):
    """One LLM call: who was asked, how long it took, tokens, and outcome."""

    __tablename__ = "inference_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InferenceStatus] = mapped_column(_STATUS_ENUM, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="inference_logs")

    # total_tokens is denormalised for easy querying; the CHECK makes it
    # impossible for it to drift from the sum.
    __table_args__ = (
        CheckConstraint(
            "total_tokens = prompt_tokens + completion_tokens",
            name="total_tokens_matches_sum",
        ),
    )
