# tracelens

Minimal inference logging for LLM calls. Wrap a chat-completions call and the
SDK records latency, tokens, and redacted input/output previews, and ships the
event to the logging service — without slowing down or ever breaking the
wrapped call.

## Install

```bash
pip install -e ./sdk
```

## Use — auto-instrumentation

`init()` patches the vendor libraries, so every call is traced with **zero
changes at the call site** — `openai`'s `chat.completions.create` and
`anthropic`'s `messages.create`, sync or async, any client instance. A vendor
that isn't installed is skipped, so tracelens keeps zero dependencies of its
own:

```python
import tracelens

tracelens.init(service="chatjippity-backend", endpoint="http://localhost:8001")

tracelens.set_meta(conversation_id=42)  # optional: tag events from this task

# plain, unmodified code — traced automatically, either vendor
response = await openai_client.chat.completions.create(model="gpt-4o", messages=messages)
response = await anthropic_client.messages.create(
    model="claude-opus-5", max_tokens=16000, messages=messages
)
```

The response is returned unchanged. If the call raises, a `failed` event is
shipped and the exception propagates as usual.

For non-OpenAI callables, the explicit wrappers still work (a re-entrancy
guard makes wrapping an already-patched method safe — no double events):

```python
response = tracelens.trace_call(some_llm_fn, model="m", messages=messages)
response = await tracelens.trace_call_async(some_async_llm_fn, model="m", messages=messages)
```

## What gets recorded

| Field | |
|---|---|
| `service`, `provider`, `model` | who made the call (`provider` is set by the patch: `openai` / `anthropic`) |
| `latency_ms` | wall time of the call |
| `prompt_tokens`, `completion_tokens`, `total_tokens` | from the response `usage` |
| `input_text` | preview of the latest user message (200 chars, PII-redacted) |
| `output_text` | preview of the assistant reply (200 chars, PII-redacted) |
| `status`, `error` | `success` or `failed` + the exception text |
| `created_at` | UTC timestamp of the call |

## Design

- **Never blocks:** events POST from a fire-and-forget daemon thread.
- **Never breaks the app:** transport errors are swallowed — a missing metric
  beats a failed response.
- **Zero dependencies:** stdlib only.
- **PII stays home:** only 200-char previews leave the process, with emails,
  phone numbers and card numbers replaced by `[REDACTED]` first. The metrics
  DB stores no message content at all.
