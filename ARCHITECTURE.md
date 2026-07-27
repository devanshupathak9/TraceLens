# Architecture

<p align="center">
  <img src="architecture.png" alt="TraceLens Architecture" width="1000">
</p>

The chat path and the observability path share only the database. The chat-api
writes `messages`; the Lambda writes `inference_logs`. Neither writes the
other's table, so a fault in the pipeline cannot corrupt or delay a chat turn.

## Ingestion flow

1. **Capture.** `tracelens.init()` patches `openai …Completions.create` and
   `anthropic …Messages.create` (sync + async) at startup. Call sites are
   unmodified. `set_meta(conversation_id=…)` is a contextvar, so the
   conversation id rides along without touching any call signature.
2. **Ship.** The event — model, provider, latency, tokens, status, redacted
   previews, UTC timestamp — POSTs to the ingestion service from a **daemon
   thread**. The traced call never waits for it.
3. **Validate.** The service parses the body with Pydantic. A malformed payload
   is a 422 and goes no further; only `model` and `latency_ms` are required.
4. **Queue.** The event is published to SQS. The service holds no state and has
   no database connection.
5. **Persist.** SQS triggers the Lambda in batches of 10. It inserts one
   `inference_logs` row per record, using the SDK's timestamp for `created_at`
   and falling back to `now()` when absent.
6. **Read.** `GET /dashboard` aggregates the rows — counts, latency, tokens,
   per-model breakdown, hourly throughput — and derives cost at read time.

**Why a queue.** Ingestion returns as soon as the event is accepted, so write
rate is decoupled from request rate: a burst waits in SQS instead of piling onto
the database, and the database can be down without ingestion failing.

## Logging strategy

- **Auto-instrumentation over explicit calls.** Wrapping every call site is
  something you forget to do; patching the vendor class can't be forgotten. The
  cost is coupling to the vendor's internal module path, which is why a missing
  vendor is skipped silently rather than raising.
- **Never break the observed app.** The daemon thread swallows every transport
  error; the ingestion service swallows publish failures after the SDK already
  has its 200. A missing metric is always preferable to a failed response.
- **Previews only.** 200 characters, with emails, phone numbers and card-like
  digit runs redacted before they leave the process. Observability data is read
  by more people and kept longer than the app's own database, so full message
  content never enters it.
- **Streaming is reported explicitly.** `create(stream=True)` returns an
  iterator before any token exists, so there is nothing to time or count at call
  time. The patch passes it through and `providers.py` calls
  `tracelens.record()` when the stream ends — which is also where token counts
  arrive (OpenAI needs `stream_options.include_usage`; Anthropic carries usage
  on the final message).

## Failure handling & assumptions

What the design assumes, stated plainly:

- **Telemetry is lossy and that is acceptable.** Chat correctness outranks
  metric completeness at every decision point. Nothing retries on the SDK side.
- **Delivery is at-least-once, never exactly-once.** A batch where one record
  fails is retried whole, so already-inserted records are inserted again.
  Duplicates are tolerable in aggregates; an idempotency key would fix it.
- **The ingestion endpoint is trusted** — it assumes a private network and
  authenticates nothing.
- **The queue is the buffer of record.** Anything the Lambda can't process stays
  in SQS or the DLQ until someone looks; there is no local write path.

| What fails | What happens |
|---|---|
| Ingestion service down or unreachable | SDK thread swallows the error. Chat unaffected; that event is lost. |
| `QUEUE_URL` unset or credentials wrong | Event is accepted, logged, dropped. Startup says `NO QUEUE_URL SET`; failures print `[bus] publish FAILED`. |
| Lambda throws (bad row, DB down) | SQS redelivers. After `maxReceiveCount` the message moves to the **DLQ** instead of blocking the queue behind it. |
| Database down | Lambda keeps failing, messages accumulate in the queue, nothing is lost until the retention window expires. |
| LLM provider fails | User message is kept, a `failed` event ships, the endpoint returns 502. |
| Client disconnects mid-reply | Provider call is cancelled and no reply is stored, so a cancelled answer can't reappear. |

**The deliberate weakness:** the SDK is silent by design, so a misconfigured
collector looks exactly like a working one from the app's side. Diagnosis starts
at the ingestion service's logs, which print every step — `[ingest]`,
`[bus] publishing`, `[bus] queued MessageId=`.

## Scaling considerations

- **The chat-api is stateless** — JWT auth, no sessions — so it scales
  horizontally. Migrations never run at startup (replicas would race the lock);
  Compose has a one-shot migrate job.
- **Streaming holds a connection for the length of a generation**, so the SSE
  endpoint opens its own database session rather than the request-scoped one,
  which would pin a pooled connection for the whole reply.
- **The queue is the shock absorber.** Ingestion is O(1) work per event;
  everything expensive happens in the Lambda, which AWS scales by queue depth.
- **The dashboard aggregates on read**, which is fine at this size and the wrong
  answer at scale: it would become a rollup table written by the Lambda, or a
  materialised view refreshed on a schedule.

## Tradeoffs made

- **Managed platforms, not Kubernetes.** Vercel + Railway + AWS Lambda. k8s was
  the one bonus item skipped — everything is containerised and would port over,
  but I hadn't used k8s before and chose to spend the remaining time making the
  pipeline work end to end rather than half-learning a deployment target.
- **A managed queue instead of Kafka/Redis Streams.** SQS gave a DLQ, retries
  and a Lambda trigger with no infrastructure to run. The cost is lock-in at
  that seam, and no replay of already-consumed events.
- **The Lambda contract is untyped.** Its input is the JSON event body, so a
  field renamed in `logging-service/schemas.py` must be renamed in
  `lambda_function.py` too, and nothing checks that. A shared schema package
  would fix it; two files felt cheaper than a third package.
- **No authentication on ingest.** Designed for a private network where the only
  caller is the backend. It is currently reachable publicly, which is the first
  thing to close.
- **Cost as a lookup table.** `pricing.py` holds per-model rates checked by
  hand; an unlisted model reports "unpriced" rather than $0 so it can't quietly
  read as free.
- **Aggregates only on the dashboard.** Deliberately deployment-wide with no
  user or conversation ids, so usage can't be attributed to a person. A
  per-conversation drill-down would need an authorisation model first.
- **No tests.** The honest one. Everything was verified by hand and by running
  the pipeline end to end; the seams that most need pinning down — the SDK
  patch, the event contract, the Lambda's SQL — are the ones with nothing
  guarding them.
