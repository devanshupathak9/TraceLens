"""
One chat turn: store the user's message, call the LLM, store the reply.

Deliberately non-streaming for now — the whole request/response cycle is one
plain JSON round trip, which is much easier to get working end to end.
Streaming (SSE) can replace the LLM call later without touching the storage
logic around it.
"""

import time

from openai import AsyncOpenAI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import Conversation, Message, MessageRole, MessageStatus


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

        start = time.perf_counter()
        try:
            reply_text, model, provider, usage = await self._complete(llm_messages)
            assistant_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=reply_text,
                status=MessageStatus.COMPLETE,
                model=model,
                provider=provider,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            # The failure becomes part of the transcript instead of a 500 — the
            # user's message is kept, and the UI shows what went wrong.
            assistant_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content="",
                status=MessageStatus.ERROR,
                model=self.settings.default_model,
                provider="openai",
                error_message=str(exc)[:2000],
                latency_ms=int((time.perf_counter() - start) * 1000),
            )

        self.session.add(assistant_message)

        # Adding messages doesn't touch the conversations row, so bump
        # updated_at by hand — it's the sidebar's sort key.
        conversation.updated_at = func.now()

        await self.session.commit()
        # server_default columns (created_at) only exist after a round trip.
        await self.session.refresh(user_message)
        await self.session.refresh(assistant_message)
        return user_message, assistant_message

    # --- internals --------------------------------------------------------

    def _build_context(
        self, conversation: Conversation, content: str
    ) -> list[dict[str, str]]:
        """System prompt + the last N completed turns + the new message."""
        history = [
            {"role": message.role.value, "content": message.content}
            for message in conversation.messages[-self.settings.max_context_messages :]
            if message.status == MessageStatus.COMPLETE
        ]
        return (
            [{"role": "system", "content": self.settings.system_prompt}]
            + history
            + [{"role": "user", "content": content}]
        )

    async def _complete(self, llm_messages: list[dict[str, str]]):
        """Returns (reply_text, model, provider, usage)."""
        settings = self.settings

        if not settings.openai_api_key:
            # No key configured: echo back, so the whole loop is testable
            # locally without an OpenAI account or spending tokens.
            return f"(echo) {llm_messages[-1]['content']}", "echo", "echo", None

        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_request_timeout_seconds,
        )
        response = await client.chat.completions.create(
            model=settings.default_model,
            messages=llm_messages,  # type: ignore[arg-type]
        )
        reply = response.choices[0].message.content or ""
        return reply, response.model, "openai", response.usage
