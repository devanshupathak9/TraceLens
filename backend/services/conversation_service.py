"""
Conversation CRUD.

Ownership is enforced here, once: every lookup is scoped to the requesting
user's id, so someone else's conversation simply doesn't exist from your point
of view. That's why "not yours" is a 404 and never a 403 — a 403 would confirm
to a guesser that the id is real.
"""


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from models import Conversation, Message


class ConversationNotFound(Exception):
    pass


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        title: str | None = None,
        model: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title or "New chat",
            model=model or get_settings().default_model,
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def list_for_user(self, user_id: int) -> list[tuple[Conversation, int]]:
        """This user's conversations, most recently active first, with message
        counts. The count comes from an outer join + group by rather than
        loading every message just to len() it."""
        stmt = (
            select(Conversation, func.count(Message.id))
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id)
            .group_by(Conversation.id)
            .order_by(Conversation.last_active_at.desc())
        )
        result = await self.session.execute(stmt)
        return [(conversation, count) for conversation, count in result.all()]

    async def get(
        self,
        conversation_id: int,
        user_id: int,
        *,
        with_messages: bool = False,
    ) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        if with_messages:
            # selectinload = one extra query for all messages, already ordered
            # by created_at (set on the relationship in models.py).
            stmt = stmt.options(selectinload(Conversation.messages))

        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ConversationNotFound
        return conversation

    async def list_messages(
        self, conversation_id: int, user_id: int
    ) -> list[Message]:
        # The get() call is the ownership check.
        conversation = await self.get(conversation_id, user_id, with_messages=True)
        return list(conversation.messages)

    async def count_messages(self, conversation_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        )
        return result.scalar_one()

    async def update(
        self,
        conversation_id: int,
        user_id: int,
        *,
        title: str | None = None,
    ) -> Conversation:
        """PATCH semantics: only the fields passed are changed."""
        conversation = await self.get(conversation_id, user_id)
        if title is not None:
            conversation.title = title
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def delete(self, conversation_id: int, user_id: int) -> None:
        conversation = await self.get(conversation_id, user_id)
        # ON DELETE CASCADE wipes the messages and inference logs in the
        # database; passive_deletes stops SQLAlchemy loading them first.
        await self.session.delete(conversation)
        await self.session.commit()
