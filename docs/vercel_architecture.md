# Vercel Architecture Plan

Vercel is the recommended entry point for the research application, but it should not run the heavy media-processing pipeline.

## What Runs on Vercel

```text
Research web UI
Read-only query API
Auth and role checks
Dashboard pages
Search and compare views
Cron trigger endpoints
```

## What Runs Outside Vercel

```text
yt-dlp media download
Podcast audio download
faster-whisper transcription
Speaker diarization
Embedding generation
Long-running retryable workers
Large file storage
```

## Proposed Cloud Components

```text
Vercel
  - Next.js research UI
  - Thin API endpoints
  - Cron trigger

Managed data services
  - Neon, Supabase, or AWS RDS PostgreSQL
  - Qdrant Cloud
  - S3 or Cloudflare R2 object storage

Worker runtime
  - AWS ECS Fargate, Google Cloud Run Jobs, Render, Railway, or Fly.io
  - Runs the Python ingestion pipeline
```

## Docker Images

Use separate images for production:

```text
Dockerfile.api     Query API only; no ffmpeg, yt-dlp, or Whisper runtime.
Dockerfile.worker  Heavy worker image for download, transcription, summary, and indexing.
```

Local Docker Compose uses the lightweight API image by default and exposes a `worker` profile for one-off worker commands:

```powershell
docker compose run --rm worker python main.py process --company NVDA --limit 1
```

The query API exposes deployment health checks:

```text
GET /healthz
GET /readyz
```

Vercel should point `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS URL of the API image, not to the worker.

## Deployment Phases

### Phase 1: Repository Readiness

- Add `.gitignore` to exclude audio, transcripts, model caches, and secrets.
- Push source code to `JasonYeh199/ceo-talk-monitor`.
- Keep current Docker Compose for local development.
- Deploy `apps/web` to Vercel as the read-only research dashboard.

### Phase 2: Read-Only Cloud App

- Connect GitHub repo to Vercel.
- Deploy a read-only UI/API that connects to managed Postgres and Qdrant.
- Keep ingestion worker local until managed worker runtime is ready.

### Phase 3: Managed Worker

- Deploy the existing Python worker image to a long-running worker platform.
- Add a job queue and job status table.
- Let Vercel Cron trigger job creation only.

### Phase 4: Production Controls

- Add SSO/RBAC.
- Add audit logs for search, export, replay, and admin actions.
- Add source policy and data retention controls.
- Add backup/restore runbooks.

## Vercel Constraints

Vercel Python Functions are suitable for FastAPI-style request/response workloads. They are not a good fit for 30-60 minute audio transcription jobs, local Whisper model loading, or persistent file storage. Keep Vercel thin and push durable work to worker infrastructure.

## Current Web App

The initial Vercel app lives in:

```text
apps/web
```

Set the Vercel project root directory to `apps/web` and configure:

```text
NEXT_PUBLIC_API_BASE_URL=https://your-fastapi-backend.example.com
```

For local development, point it at:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
