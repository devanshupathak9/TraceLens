import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
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


class MessageStatus(str, enum.Enum):
    """Terminal state of an assistant message; user messages are always COMPLETE."""

    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"


# Stored as VARCHAR + CHECK rather than a native Postgres ENUM type. Native enums
# require ALTER TYPE to add a value, which can't run inside a transaction in older
# Postgres and makes migrations awkward for no real benefit at this scale.
_ROLE_ENUM = SAEnum(MessageRole, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])
_STATUS_ENUM = SAEnum(MessageStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])


class TimestampMixin:
    """Created/updated columns, defaulted by the database rather than Python."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base, TimestampMixin):
    """
    A chat user, either registered or a guest.

    Guests are real rows rather than a separate concept, keyed on the device id
    the browser generates. That's what lets `POST /auth/guest` be idempotent, and
    what lets a guest later upgrade to a permanent account by having `email` and
    `password_hash` filled in on this same row — so their conversations survive
    without being moved.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Nullable because guests have neither. Unique so registration fails loudly
    # on a duplicate rather than silently creating a second account.
    username: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))

    is_guest: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Kept after an upgrade, so a returning browser still resolves to this user.
    device_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # A guest needs a device id; a registered user needs credentials. Enforced
        # in the database because an application bug that writes a half-formed
        # user is much harder to find later than a failed insert now.
        CheckConstraint(
            "(is_guest = true AND device_id IS NOT NULL)"
            " OR (is_guest = false AND email IS NOT NULL AND password_hash IS NOT NULL)",
            name="guest_has_device_or_user_has_credentials",
        ),
    )

    def __repr__(self) -> str:
        who = self.email or f"guest:{self.device_id}"
        return f"<User {self.id} {who}>"


class Conversation(Base, TimestampMixin):
    """A chat thread belonging to one user."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ondelete CASCADE at the database level, with passive_deletes on the
    # relationship so deleting a user is one statement instead of SQLAlchemy
    # loading every child row to delete it individually.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), default="New chat", nullable=False)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )

    __table_args__ = (
        # Covers the sidebar query: this user's conversations, newest first.
        # No explicit DESC — Postgres scans a btree backwards just as cheaply, and
        # naming the mixin's column here would not resolve at class-body scope.
        Index("ix_conversations_user_id_updated_at", "user_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} {self.title!r}>"


class Message(Base):
    """
    One turn in a conversation.

    Token counts and model are denormalised onto the message so the transcript is
    self-describing without joining telemetry — the inference log in the other
    half of the system is the authoritative record for observability, but a
    message should still be readable on its own.

    No `updated_at`: messages are append-only. Editing a turn would invalidate
    every reply that followed it, so the UI creates a new message instead.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[MessageRole] = mapped_column(_ROLE_ENUM, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[MessageStatus] = mapped_column(
        _STATUS_ENUM, default=MessageStatus.COMPLETE, nullable=False
    )

    # Null on user messages, and on assistant messages that failed before the
    # provider was reached.
    model: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str | None] = mapped_column(String(50))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        # Covers loading a transcript in order, and building the context window.
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message {self.id} {self.role.value} {len(self.content)}ch>"
