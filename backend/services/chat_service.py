"""
One chat turn: store the user's message, call the LLM, store the reply, and
record the call in inference_logs.

Messages hold only the transcript; every LLM call — success or failure — gets
an InferenceLog row with provider, model, tokens, latency, and status. That's
the separation the schema is built around.

Deliberately non-streaming for now: one plain JSON round trip, easy to verify
end to end. Streaming can replace the LLM call later without touching the
storage logic around it.
"""

import time

from openai import AsyncOpenAI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import (
    Conversation,
    InferenceLog,
    InferenceStatus,
    Message,
    MessageRole,
)


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

        start = time.perf_counter()
        try:
            reply_text, provider, usage = await self._complete(
                conversation.model, llm_messages
            )
        except Exception as exc:
            # The user's message and the failed call are still recorded — the
            # transcript keeps the question, and the log keeps the failure.
            self.session.add(
                InferenceLog(
                    conversation_id=conversation.id,
                    provider="openai",
                    model=conversation.model,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    status=InferenceStatus.FAILED,
                )
            )
            conversation.last_active_at = func.now()
            await self.session.commit()
            raise LLMCallFailed(str(exc))

        latency_ms = int((time.perf_counter() - start) * 1000)

        assistant_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=reply_text,
        )
        self.session.add(assistant_message)

        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        self.session.add(
            InferenceLog(
                conversation_id=conversation.id,
                provider=provider,
                model=conversation.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                status=InferenceStatus.SUCCESS,
            )
        )

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

    async def _complete(self, model: str, llm_messages: list[dict[str, str]]):
        """Returns (reply_text, provider, usage)."""
        settings = self.settings

        if not settings.openai_api_key:
            # No key configured: echo back, so the whole loop is testable
            # locally without an OpenAI account or spending tokens.
            return f"(echo) {llm_messages[-1]['content']}", "echo", None

        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_request_timeout_seconds,
        )
        response = await client.chat.completions.create(
            model=model,
            messages=llm_messages,  # type: ignore[arg-type]
        )
        reply = response.choices[0].message.content or ""
        return reply, "openai", response.usage
