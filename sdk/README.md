# tracelens

Inference logging for LLM applications. Wraps the OpenAI client so every call is
recorded — model, latency, tokens, status, previews — and shipped to an ingestion
service in the background.

## Install

```bash
pip install -e ./sdk
```

## Use

```python
import tracelens

tracelens.init(
    service="chat-api",
    endpoint="http://localhost:8001",
    api_key=None,          # set when the ingestion service requires one
)
```

That's it. Existing OpenAI calls are now recorded without modification:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()

stream = await client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "hello"}],
    stream=True,
    stream_options={"include_usage": True},   # needed for token counts
)
```

### Correlating calls to a conversation

Auto-instrumentation means nothing is passed at the call site, so ids come from
ambient context:

```python
from tracelens import trace_context

with trace_context(conversation_id=str(conversation.id), user_id=str(user.id)):
    stream = await client.chat.completions.create(...)
```

Backed by `contextvars`, so it follows `await` boundaries and concurrent requests
don't read each other's ids.

## What gets recorded

| Field | Notes |
|---|---|
| `provider`, `model`, `operation` | |
| `status` | `success` / `error` / `cancelled` |
| `latency_ms` | monotonic clock, so NTP can't make it negative |
| `time_to_first_token_ms` | streamed calls only; the number users actually feel |
| `prompt_tokens`, `completion_tokens` | needs `stream_options={"include_usage": True}` |
| `input_preview`, `output_preview` | truncated and redacted; full prompts never leave |
| `conversation_id`, `session_id`, `user_id`, `request_id` | from `trace_context` |
| `error_type`, `error_message` | on failure |

## Design notes

**Never blocks the caller.** `send()` appends to a bounded in-memory queue and
returns; a background thread batches and POSTs. If ingest latency landed on the
user's chat response, the SDK would be a net negative.

**Never breaks the caller.** Every instrumentation path swallows its own
exceptions. A missing metric is a much better outcome than a failed response.

**Bounded queue, at-most-once delivery.** When the queue is full, events are
dropped and counted. An unbounded queue would turn an ingestion outage into
unbounded memory growth in the application the SDK is meant to observe. Real
durability would need a disk-backed queue; for observability data this is the right
trade.

**Redaction happens before truncation.** Truncating first can cut a pattern in half
and leave a recognisable fragment — half a card number is still a disclosure.

**PII redaction is pattern matching, not a guarantee.** It catches emails, API
keys, bearer tokens, JWTs, card numbers, SSNs, IPs, and phone numbers. It will not
catch a name or an address in prose.

## Streaming, and why it's the hard part

A streamed call returns immediately with an iterator, so the call isn't over when
the method returns. The SDK returns a wrapper that passes chunks through unchanged
and emits the event in a `finally`, so the record fires whether the stream
completed, raised, or was abandoned mid-way.

Two details that are easy to get wrong:

- The final usage-bearing chunk has an **empty `choices` list**. Indexing it
  unconditionally raises `IndexError` at the very end of every stream.
- Token counts arrive **only** if the caller passed
  `stream_options={"include_usage": True}`. Without it, usage is silently null
  while everything else looks correct.

## Checking it works

```python
tracelens.flush()      # block until queued events are sent
tracelens.stats()      # {'sent': 12, 'failed': 0, 'dropped': 0, 'queued': 0}
```

Then read them back from the ingestion service:

```bash
curl localhost:8001/v1/events | jq
curl localhost:8001/v1/stats  | jq
```
