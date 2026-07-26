# tracelens

Minimal inference logging for LLM calls. Wrap a chat-completions call and the
SDK records latency, tokens, input and output text, and ships the event to the
logging service — without slowing down or ever breaking the wrapped call.

## Install

```bash
pip install -e ./sdk
```

## Use

```python
import tracelens

tracelens.init(service="chatjippity-backend", endpoint="http://localhost:8001")

# sync client
response = tracelens.trace_call(
    client.chat.completions.create,
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)

# async client
response = await tracelens.trace_call_async(
    client.chat.completions.create,
    model="gpt-4o",
    messages=messages,
)
```

The response is returned unchanged. If the call raises, a `failed` event is
shipped and the exception propagates as usual.

## What gets recorded

| Field | |
|---|---|
| `service`, `provider`, `model` | who made the call |
| `latency_ms` | wall time of the call |
| `prompt_tokens`, `completion_tokens`, `total_tokens` | from the response `usage` |
| `input_text` | the messages sent, as JSON |
| `output_text` | the assistant reply |
| `status`, `error` | `success` or `failed` + the exception text |

## Design

- **Never blocks:** events POST from a fire-and-forget daemon thread.
- **Never breaks the app:** transport errors are swallowed — a missing metric
  beats a failed response.
- **Zero dependencies:** stdlib only.
