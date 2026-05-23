# Operations Runbook

This runbook keeps the production MVP small: one public API, one Postgres database, one Vercel dashboard, and one scheduled worker command.

## Daily Ingestion

Use the worker image, not the API image, for ingestion:

```powershell
python main.py job daily-ingest --source all --limit 3
```

The safer smoke-test version stores candidate metadata only:

```powershell
python main.py job daily-ingest --source youtube --company NVDA --limit 3 --metadata-only
```

This metadata-only smoke test can run as a Render one-off job on the API service image. Full audio download, transcription, and summary jobs should use `Dockerfile.worker`.

If Render returns `new paid services not allowed`, the account cannot create one-off jobs yet. The API and dashboard can still read existing data, but scheduled ingestion should remain pending until a paid job/worker runtime or another scheduler is available.

The command records every run in `ingestion_runs`. Check the latest runs with:

```text
GET /jobs
```

## Overlap Protection

`daily-ingest` skips a new run if another run has been in `running` status within the lock TTL. The default TTL is 180 minutes:

```powershell
python main.py job daily-ingest --source all --limit 3 --lock-ttl-minutes 180
```

Set `--lock-ttl-minutes 0` only when manually recovering a stuck job.

## Cloud Environment

API and worker containers should share these variables:

```text
DATABASE_URL=postgresql+psycopg://...
QDRANT_URL=https://...
QDRANT_API_KEY=
APP_CONFIG_PATH=/app/config.yaml
OPENAI_API_KEY=
OPENAI_SUMMARY_MODEL=gpt-4.1-mini
LOG_LEVEL=INFO
```

Leave `QDRANT_URL` empty until Qdrant Cloud is ready. The API will still serve text search, talks, compare, and job status.

## Production Checks

```text
GET /healthz
GET /readyz
GET /companies
GET /talks?company=NVDA
GET /compare?company=NVDA&topic=AI%20demand
GET /jobs
```
