import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class InferenceStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


# Stored as VARCHAR + CHECK rather than a native Postgres ENUM type. Native enums
# require ALTER TYPE to add a value, which makes migrations awkward for no real
# benefit at this scale.
_ROLE_ENUM = SAEnum(MessageRole, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])
_INFERENCE_STATUS_ENUM = SAEnum(InferenceStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Stored lowercased; unique so a duplicate registration fails loudly
    # instead of silently creating a second account.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ondelete CASCADE at the database level, with passive_deletes on the
    # relationship, so deleting a user is one statement instead of SQLAlchemy
    # loading every child row to delete it individually.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), default="New chat", nullable=False)
    # The model this conversation talks to, fixed at creation (defaulted from
    # settings when the client doesn't pick one).
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Bumped on every new message — the sidebar's sort key. Indexed for the
    # "recent conversations" ordering.
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )
    inference_logs: Mapped[list["InferenceLog"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} {self.title!r}>"


class Message(Base):
    """
    One turn in a conversation — just the transcript.

    Deliberately lean: model, tokens, latency, and errors live in
    `inference_logs`, so the chat transcript and the observability record are
    separate concerns.

    No `updated_at`: messages are append-only.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped[MessageRole] = mapped_column(_ROLE_ENUM, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id} {self.role.value} {len(self.content)}ch>"


class InferenceLog(Base):
    """
    One LLM call: what was asked of which provider/model, how long it took,
    what it cost in tokens, and whether it worked.
    """

    __tablename__ = "inference_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # 0 rather than NULL when the provider reports nothing — the columns are
    # NOT NULL so aggregates never have to reason about missing values.
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InferenceStatus] = mapped_column(_INFERENCE_STATUS_ENUM, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="inference_logs")

    def __repr__(self) -> str:
        return f"<InferenceLog {self.id} {self.model} {self.status.value}>"
