"""
One chat turn: store the user's message, call the LLM, store the reply.

The backend no longer writes inference_logs itself — the tracelens SDK wraps
the LLM call and ships latency/tokens/text to the logging service, whose lambda
persists the row. The chat path stays fast; observability rides alongside.
"""

import asyncio
from collections.abc import AsyncIterator

import tracelens
from fastapi import Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import Conversation, Message, MessageRole
from providers import provider_for


class LLMCallFailed(Exception):
    pass


class ClientDisconnected(Exception):
    pass


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def send_message(
        self, conversation: Conversation, content: str, request: Request | None = None
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
            reply_text = await self._complete_or_cancel(conversation, llm_messages, request)
        except ClientDisconnected:
            # User hit stop: keep their message, store no reply.
            conversation.last_active_at = func.now()
            await self.session.commit()
            raise
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

    async def stream_message(
        self, conversation: Conversation, content: str
    ) -> AsyncIterator[tuple[str, object]]:
        """
        One streamed chat turn, as `(kind, payload)` pairs for the SSE layer:
        `("delta", text)` per token, then one `("done", (user, assistant))`.

        Cancellation is the caller's disconnect: FastAPI throws into this
        generator, so the `except asyncio.CancelledError` path is what stops us
        from persisting a reply nobody is listening for.
        """
        user_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=content,
        )
        self.session.add(user_message)

        if conversation.title == "New chat" and not conversation.messages:
            conversation.title = content[:50]

        llm_messages = self._build_context(conversation, content)
        provider = provider_for(conversation.model, self.settings)
        tracelens.set_meta(conversation_id=conversation.id)

        reply = ""
        try:
            if provider is None:
                reply = f"(echo) {content}"
                yield "delta", reply
            else:
                async for delta in provider.stream(conversation.model, llm_messages):
                    reply += delta
                    yield "delta", delta
        except asyncio.CancelledError:
            # Client hung up mid-generation: keep their message, store no reply.
            conversation.last_active_at = func.now()
            await self.session.commit()
            raise
        except Exception as exc:
            conversation.last_active_at = func.now()
            await self.session.commit()
            raise LLMCallFailed(str(exc))

        assistant_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=reply,
        )
        self.session.add(assistant_message)
        conversation.last_active_at = func.now()
        await self.session.commit()
        await self.session.refresh(user_message)
        await self.session.refresh(assistant_message)
        yield "done", (user_message, assistant_message)

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

    async def _complete_or_cancel(
        self,
        conversation: Conversation,
        llm_messages: list[dict[str, str]],
        request: Request | None,
    ) -> str:
        """Run the LLM call, but abandon it the moment the client disconnects.

        Without this, "stop generating" only aborts the browser's fetch — the
        backend would keep waiting on OpenAI, store the reply, and the message
        would reappear on the next load.
        """
        llm_task = asyncio.create_task(self._complete(conversation, llm_messages))
        if request is None:
            return await llm_task

        disconnect_task = asyncio.create_task(self._wait_for_disconnect(request))
        try:
            done, _ = await asyncio.wait(
                {llm_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if llm_task in done:
                return llm_task.result()
            llm_task.cancel()
            raise ClientDisconnected()
        finally:
            disconnect_task.cancel()

    @staticmethod
    async def _wait_for_disconnect(request: Request) -> None:
        while not await request.is_disconnected():
            await asyncio.sleep(0.5)

    async def _complete(
        self, conversation: Conversation, llm_messages: list[dict[str, str]]
    ) -> str:
        provider = provider_for(conversation.model, self.settings)

        if provider is None:
            # No key configured for this model's provider: echo back, so the
            # whole loop is testable locally without spending tokens.
            return f"(echo) {llm_messages[-1]['content']}"

        # The SDK auto-instruments the vendor clients at init(); set_meta tags
        # the traced event with the conversation without touching the call.
        tracelens.set_meta(conversation_id=conversation.id)
        return await provider.complete(conversation.model, llm_messages)
