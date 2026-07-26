"""
One chat turn: store the user's message, call the LLM, store the reply.

The backend no longer writes inference_logs itself — the tracelens SDK wraps
the LLM call and ships latency/tokens/text to the logging service, whose lambda
persists the row. The chat path stays fast; observability rides alongside.
"""

import tracelens
from openai import AsyncOpenAI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import Conversation, Message, MessageRole


class LLMCallFailed(Exception):
    pass


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def send_message(
        self, conversation: Conversation, content: str
    ) -> tuple[Message, Message]:
        """
        `conversation` must be loaded with its messages — they are the context
        window for the LLM call.
        """
        user_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=content,
        )
        self.session.add(user_message)

        # First message names the conversation, like ChatGPT does.
        if conversation.title == "New chat" and not conversation.messages:
            conversation.title = content[:50]

        llm_messages = self._build_context(conversation, content)

        try:
            reply_text = await self._complete(conversation, llm_messages)
        except Exception as exc:
            # Keep the user's message; the SDK already shipped the failed event.
            conversation.last_active_at = func.now()
            await self.session.commit()
            raise LLMCallFailed(str(exc))

        assistant_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=reply_text,
        )
        self.session.add(assistant_message)

        # Adding messages doesn't touch the conversations row, so bump
        # last_active_at by hand — it's the sidebar's sort key.
        conversation.last_active_at = func.now()

        await self.session.commit()
        # server_default columns (created_at) only exist after a round trip.
        await self.session.refresh(user_message)
        await self.session.refresh(assistant_message)
        return user_message, assistant_message

    # --- internals --------------------------------------------------------

    def _build_context(
        self, conversation: Conversation, content: str
    ) -> list[dict[str, str]]:
        """System prompt + the last N turns + the new message."""
        history = [
            {"role": message.role.value, "content": message.content}
            for message in conversation.messages[-self.settings.max_context_messages :]
        ]
        return (
            [{"role": "system", "content": self.settings.system_prompt}]
            + history
            + [{"role": "user", "content": content}]
        )

    async def _complete(
        self, conversation: Conversation, llm_messages: list[dict[str, str]]
    ) -> str:
        settings = self.settings

        if not settings.openai_api_key:
            # No key configured: echo back, so the whole loop is testable
            # locally without an OpenAI account or spending tokens.
            return f"(echo) {llm_messages[-1]['content']}"

        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_request_timeout_seconds,
        )
        response = await tracelens.trace_call_async(
            client.chat.completions.create,
            _tracelens={"conversation_id": conversation.id},
            model=conversation.model,
            messages=llm_messages,
        )
        return response.choices[0].message.content or ""
