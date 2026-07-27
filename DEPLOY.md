# Deploying TraceLens

Target setup: **Vercel** (frontend) + **Render** (chat-api + logging-service, Docker) +
**Supabase** (Postgres) + **AWS SQS → Lambda** (event pipeline).

```
Vercel (frontend) ─rewrite /api/*→ Render chat-api ─SDK event→ Render logging-service
                                                                     │ QUEUE_URL set
                                                                     ▼
                                                              AWS SQS queue
                                                                     │ trigger
                                                                     ▼
                                                              AWS Lambda ──INSERT──▶ Supabase
```

## 0. Supabase (already done)

Migrations are applied by running locally once: `cd backend && ./run_local.sh`
(or `alembic upgrade head`). Grab **two** connection strings from
Supabase → Connect:

- **Session pooler** URI (host `aws-0-<region>.pooler.supabase.com`, port 5432).
  Use this everywhere below. The direct `db.<ref>.supabase.co` host is
  IPv6-only and unreachable from AWS Lambda and most PaaS hosts.
- Backend needs the scheme changed to `postgresql+asyncpg://`; the Lambda uses
  plain `postgresql://`.

## 1. AWS: SQS + Lambda (do this first — the logging service needs the queue URL)

### Queue
SQS → Create queue → **Standard**, name `tracelens-events`. Defaults are fine.
Copy the **Queue URL** and **ARN**.

### Lambda function
Build the zip on your Mac (psycopg2 must be the Linux build):

```bash
cd lambda
mkdir -p package
pip install psycopg2-binary --platform manylinux2014_x86_64 \
    --python-version 3.12 --only-binary=:all: -t package
cp lambda_function.py package/
cd package && zip -r ../lambda.zip . && cd ..
```

Lambda → Create function → Author from scratch → Python 3.12, arch x86_64.
Then:
- Upload `lambda.zip` (Code → Upload from → .zip file).
- Handler: `lambda_function.lambda_handler` (the default).
- Configuration → Environment variables: `DATABASE_URL` = Supabase **session
  pooler** URI (plain `postgresql://`).
- Configuration → General: timeout **10 s**.

### Wire SQS → Lambda (minimal security)
- Lambda → Configuration → Permissions → click the execution role → Attach
  policies → **`AWSLambdaSQSQueueExecutionRole`** (grants receive/delete on SQS
  + CloudWatch logs — that's all the Lambda needs).
- Lambda → Add trigger → SQS → pick `tracelens-events`, batch size 10.

### Publisher credentials for the logging service
IAM → Users → Create user `tracelens-publisher` (no console access) → Create
**inline policy** (send-only, this queue only):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "sqs:SendMessage",
    "Resource": "<QUEUE ARN>"
  }]
}
```

Create an **access key** for it — these become env vars on the logging service.

## 2. Render: the two backends

Both use the existing Dockerfiles, which expect the **repo root** as build
context — Render does exactly that when you set only "Dockerfile Path".

### chat-api
New → Web Service → this repo:
- Dockerfile path: `backend/Dockerfile` (leave Root Directory empty)
- Env vars:
  - `DATABASE_URL` = `postgresql+asyncpg://...pooler.supabase.com:5432/postgres`
  - `JWT_SECRET` = long random string
  - `OPENAI_API_KEY` = your key
  - `TRACELENS_INGEST_URL` = `https://<logging-service>.onrender.com` (add after step below)
  - `PORT` = `8000`

### logging-service
New → Web Service → this repo:
- Root Directory: `logging-service` (its Dockerfile is self-contained)
- Env vars:
  - `QUEUE_URL` = queue URL from step 1 — **required**; without it every event
    is dropped after being logged
  - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` = the publisher key
  - `AWS_DEFAULT_REGION` = queue's region, e.g. `ap-south-1`
  - `PORT` = `8001`

(No `DATABASE_URL` here — this service never touches the DB; the Lambda does
all the writing.)

Deploy logging-service first, then paste its URL into chat-api's
`TRACELENS_INGEST_URL`.

## 3. Vercel: frontend

- Edit `frontend/vercel.json`: replace `YOUR-CHAT-API.onrender.com` with the
  real chat-api Render URL, commit, push.
- Vercel → New Project → import the repo → **Root Directory: `frontend`**.
  It auto-detects Vite (build `npm run build`, output `dist`).

The `vercel.json` rewrite proxies `/api/*` from the Vercel domain to Render, so
the browser only ever talks to one origin — no CORS changes needed.

## 4. Smoke test

1. Open the Vercel URL, register, send a message.
2. Render logging-service logs show the ingested event.
3. SQS queue metrics show a message in/out; Lambda → Monitor → CloudWatch logs
   show `event: {...}`.
4. Supabase table editor: new row in `inference_logs`; the in-app Dashboard
   shows the call.
