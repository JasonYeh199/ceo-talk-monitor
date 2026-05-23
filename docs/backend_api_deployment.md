# Public API Deployment

The Vercel dashboard needs a public FastAPI URL. A local URL such as `http://localhost:8000` works only on your machine and will fail from Vercel.

## Target Runtime

Deploy the query API with:

```text
Dockerfile.api
```

Use the worker image separately for ingestion and transcription:

```text
Dockerfile.worker
```

## Required API Environment

```text
DATABASE_URL=postgresql+psycopg://...
QDRANT_URL=https://...
APP_CONFIG_PATH=/app/config.yaml
OPENAI_API_KEY=
OPENAI_SUMMARY_MODEL=gpt-4.1-mini
LOG_LEVEL=INFO
```

The API container must pass:

```text
GET /healthz
GET /readyz
```

## Connect Vercel

After the API has a public HTTPS URL, set this in the Vercel web project:

```text
NEXT_PUBLIC_API_BASE_URL=https://your-api-host.example.com
```

Redeploy the Vercel project after changing the environment variable.

## Sync Local MVP Data

To copy already processed local metadata, transcripts, and summaries to the cloud Postgres database:

```powershell
$env:CLOUD_DATABASE_URL="<Render external database URL>"
docker compose run --rm -e CLOUD_DATABASE_URL -v ${PWD}/scripts:/app/scripts:ro app python scripts/sync_cloud_db.py
```

If using Render Postgres from outside Render, add your current IP to the database allow list first.

## Data Flow

1. Worker ingests CNBC YouTube or podcast sources.
2. Worker writes metadata, transcripts, and summaries to Postgres.
3. Worker writes embeddings to Qdrant.
4. FastAPI serves `/companies`, `/talks`, `/search`, and `/compare`.
5. Vercel dashboard fetches the FastAPI URL through `NEXT_PUBLIC_API_BASE_URL`.
