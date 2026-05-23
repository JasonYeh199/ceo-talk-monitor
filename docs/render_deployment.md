# Render Deployment

Use Render for the public FastAPI query API. Vercel remains responsible for the Next.js dashboard.

## Why Render

The API is a Docker service and needs to connect to Postgres. Render supports Docker-based web services, managed Postgres, HTTP health checks, and Blueprint files.

## Deploy The API

1. In Render, create a new Blueprint from `JasonYeh199/ceo-talk-monitor`.
2. Render will read `render.yaml`.
3. Confirm the `ceo-talk-monitor-api` web service and `ceo-talk-monitor-db` Postgres database.
4. Deploy.

The API service uses:

```text
Dockerfile.api
GET /healthz
GET /readyz
```

Render should produce a public URL similar to:

```text
https://ceo-talk-monitor-api.onrender.com
```

Verify:

```text
https://ceo-talk-monitor-api.onrender.com/healthz
https://ceo-talk-monitor-api.onrender.com/readyz
https://ceo-talk-monitor-api.onrender.com/companies
```

## Connect Vercel

In the Vercel web project, set:

```text
NEXT_PUBLIC_API_BASE_URL=https://ceo-talk-monitor-api.onrender.com
```

Then redeploy Vercel.

## Qdrant

The Render blueprint leaves `QDRANT_URL` blank. This keeps text search and metadata queries working while avoiding a failing localhost vector connection in the API service.

For vector search, create a Qdrant Cloud cluster and set:

```text
QDRANT_URL=https://...
```

Then run ingestion/processing with the same `QDRANT_URL`.

## Seed Data

The API database starts with configured companies on boot. To populate talks and summaries, run ingestion against the cloud database from a trusted worker environment:

```powershell
$env:DATABASE_URL="<Render external database URL>"
$env:QDRANT_URL="<Qdrant URL, optional>"
python main.py init-db
python main.py ingest --source youtube --company NVDA --limit 3
```

For production, run ingestion with `Dockerfile.worker` on a scheduled worker or job service instead of your laptop.
