"""
LLM provider abstraction.

One `Protocol` plus concrete adapters, so adding Anthropic or Gemini later means
a new class and a registry entry rather than touching the chat route.

Structure only — bodies raise NotImplementedError.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from config import Settings, get_settings
from models import MessageRole


@dataclass(slots=True)
class ChatMessage:
    """One turn sent to the provider. Deliberately not the ORM model."""

    role: MessageRole
    content: str


@dataclass(slots=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


@dataclass(slots=True)
class TextDelta:
    """A chunk of generated text."""

    text: str


@dataclass(slots=True)
class StreamFinished:
    """
    Final event of a stream, carrying the metadata the telemetry SDK needs.

    Usage arrives at the *end* of a stream, not with each chunk — and only if it
    was requested. For OpenAI that means passing
    `stream_options={"include_usage": True}`; omit it and token counts are simply
    absent, which is easy to miss because the stream otherwise looks fine.
    """

    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)


ProviderEvent = TextDelta | StreamFinished


class ProviderError(Exception):
    """
    Provider call failed.

    `retryable` distinguishes a rate limit or timeout from a bad request, so the
    caller can decide whether trying again could possibly help.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    """
    Interface every provider implements.

    Streaming-only on purpose: a non-streaming call is just a stream consumed to
    completion, and having one code path avoids two ways to be wrong.
    """

    name: str
    default_model: str

    @abstractmethod
    def stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """
        Stream a completion.

        Yields zero or more `TextDelta` and exactly one `StreamFinished` last.
        Must raise `ProviderError` for provider failures rather than leaking
        vendor exception types to the route.

        Cancellation arrives as `asyncio.CancelledError` when the client
        disconnects — let it propagate so the upstream HTTP request is actually
        torn down instead of continuing to bill.
        """
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    """Adapter over the official `openai` async client."""

    name = "openai"

    def __init__(self, api_key: str, default_model: str) -> None:
        self.default_model = default_model
        raise NotImplementedError

    async def stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """
        Implementation notes:

        - `stream=True` plus `stream_options={"include_usage": True}`, otherwise
          the final usage chunk never arrives and token counts log as null.
        - The usage-bearing final chunk has an empty `choices` list, so guard
          index access or it raises IndexError at the very end of every stream.
        - Map `openai.RateLimitError` and `openai.APITimeoutError` to
          `ProviderError(retryable=True)`, everything else to retryable=False.
        """
        raise NotImplementedError


class EchoProvider(LLMProvider):
    """
    Fake provider that streams a canned reply word by word.

    Exists so the UI, streaming, cancellation, and the telemetry pipeline are all
    testable with no API key and no spend. Selected automatically when
    OPENAI_API_KEY is unset, which is why the app runs from a bare checkout.

    Should sleep briefly between words so streaming is visible, and report
    plausible token counts so dashboards have something to plot.
    """

    name = "echo"

    def __init__(self, default_model: str = "echo-1", delay_seconds: float = 0.04) -> None:
        self.default_model = default_model
        self.delay_seconds = delay_seconds

    async def stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        raise NotImplementedError


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """
    Pick a provider from configuration.

    Returns `OpenAIProvider` when OPENAI_API_KEY is set, otherwise
    `EchoProvider`. Falling back rather than raising is deliberate: a missing key
    should degrade the app to a working demo, not prevent it from starting.

    Worth caching (`functools.lru_cache`) so the underlying HTTP client and its
    connection pool are reused across requests.
    """
    settings = settings or get_settings()
    raise NotImplementedError
