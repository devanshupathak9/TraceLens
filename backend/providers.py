"""LLM providers as strategies.

`ChatService` asks `provider_for(model)` for a strategy and calls
`provider.complete(...)` — it never knows which vendor is behind it. Adding a
provider means adding one class and one line in the registry.
"""

import time
from collections.abc import AsyncIterator
from typing import Protocol

import anthropic
import tracelens
from openai import AsyncOpenAI

from config import Settings

# Anthropic replies need an explicit output cap; generous enough for chat.
ANTHROPIC_MAX_TOKENS = 16000


class LLMProvider(Protocol):
    name: str

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str: ...

    def stream(
        self, model: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]: ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_request_timeout_seconds,
        )

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        response = await self._client().chat.completions.create(
            model=model, messages=messages
        )
        return response.choices[0].message.content or ""

    async def stream(
        self, model: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        start = time.perf_counter()
        text = ""
        usage = None
        # include_usage adds a final chunk carrying token counts; without it a
        # streamed call reports no tokens at all.
        stream = await self._client().chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        try:
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.choices and (delta := chunk.choices[0].delta.content):
                    text += delta
                    yield delta
        except Exception as exc:
            _record_stream(self.name, model, messages, text, start, usage, error=exc)
            raise
        _record_stream(self.name, model, messages, text, start, usage)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(
            api_key=self.settings.anthropic_api_key,
            timeout=self.settings.llm_request_timeout_seconds,
        )

    @staticmethod
    def _split(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Anthropic takes the system prompt as a parameter, not a message."""
        system = ""
        chat = []
        for message in messages:
            if message["role"] == "system":
                system = message["content"]
            else:
                chat.append(message)
        return system, chat

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        system, chat = self._split(messages)
        response = await self._client().messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            system=system,
            messages=chat,
        )
        return "".join(block.text for block in response.content if block.type == "text")

    async def stream(
        self, model: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        system, chat = self._split(messages)
        start = time.perf_counter()
        text = ""
        usage = None
        try:
            async with self._client().messages.stream(
                model=model,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                system=system,
                messages=chat,
            ) as stream:
                async for delta in stream.text_stream:
                    text += delta
                    yield delta
                usage = (await stream.get_final_message()).usage
        except Exception as exc:
            _record_stream(self.name, model, messages, text, start, usage, error=exc)
            raise
        _record_stream(self.name, model, messages, text, start, usage)


def _record_stream(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_text: str,
    start: float,
    usage,
    error: Exception | None = None,
) -> None:
    """Report a streamed call to tracelens once the stream has finished."""
    last = messages[-1] if messages else {}
    tracelens.record(
        provider=provider,
        model=model,
        latency_ms=int((time.perf_counter() - start) * 1000),
        input_text=last.get("content", ""),
        output_text=output_text,
        usage=usage,
        status="failed" if error is not None else "success",
        error=error,
    )


def provider_for(model: str, settings: Settings) -> LLMProvider | None:
    """Pick the strategy for a model name; None means no usable provider
    (missing API key) and the caller falls back to echo mode."""
    if model.startswith("claude"):
        return AnthropicProvider(settings) if settings.anthropic_api_key else None
    return OpenAIProvider(settings) if settings.openai_api_key else None
