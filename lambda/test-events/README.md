# Lambda test events

Sample payloads for exercising `lambda_function.py` from the AWS console
(Lambda → Test → paste one in) or the CLI. They cover both providers, a failed
call, a batch, and the missing-timestamp fallback.

**Set `conversation_id` to a real id from your `conversations` table first.**
`inference_logs.conversation_id` is a foreign key, so a nonexistent id fails
the insert — which reads like a broken function but is only a bad test id.

| File | Shape | What it covers | Expect |
|---|---|---|---|
| `01-openai-success.json` | SQS | a normal OpenAI call | `stored 1`, one row |
| `02-anthropic-success.json` | SQS | Anthropic, different model + token split | `stored 1`, one row |
| `03-failed-call.json` | SQS | `status: failed`, zero tokens, error text | `stored 1`, one row |
| `04-batch-mixed.json` | SQS | 3 records, one of them incomplete | `stored 3`, **two** rows |
| `05-direct-no-timestamp.json` | direct | no `created_at`, bare (non-SQS) event | `stored`, `created_at` = now() |

Two results that look wrong but aren't:

- **`04` says `stored 3` but writes 2 rows.** The third record has no `model`,
  so it is skipped with `skipped: missing conversation_id, model or latency_ms`
  while the batch continues. The count in the return message is records
  received, not rows written.
- **`05` returns `stored`, not `stored 1`.** A payload with no `Records` key is
  treated as a single direct invoke, which is the path the console uses when
  you don't wrap the event.

## Running them

Console: Lambda → your function → Test → create a new event → paste the file.

CLI:

```bash
aws lambda invoke --function-name tracelens-worker \
    --payload fileb://01-openai-success.json /dev/stdout
```

## Checking the result

```sql
SELECT id, provider, model, prompt_tokens, completion_tokens,
       latency_ms, status, created_at
FROM inference_logs ORDER BY id DESC LIMIT 5;
```

`created_at` should be the timestamp from the event (`09:15:00Z` for `01`), not
the time you ran the test. **If it shows the current time instead, the function
is still running a zip built before `created_at` was passed through** — rebuild
with `../build.sh` and re-upload.
