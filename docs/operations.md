# Operations Runbook

This runbook keeps the production MVP small: one public API, one Postgres database, one Vercel dashboard, and one scheduled worker command.

## Daily Ingestion

Use the worker image, not the API image, for ingestion:

```powershell
python main.py job daily-ingest --source all --limit 3
```

The safer smoke-test version stores candidate metadata only:

```powershell
python main.py job daily-ingest --source youtube --limit 1 --metadata-only
```

This metadata-only smoke test can run as a Render one-off job on the API service image. Full audio download, transcription, and summary jobs should use `Dockerfile.worker`.

If Render returns `new paid services not allowed`, the account cannot create one-off jobs yet. The API and dashboard can still read existing data, but scheduled ingestion should remain pending until a paid job/worker runtime or another scheduler is available.

The command records every run in `ingestion_runs`. Check the latest runs with:

```text
GET /jobs
```

## Relevance Curation

Re-run relevance scoring against stored pending candidates and mark stale false positives as `rejected`:

```powershell
python main.py job curate-relevance --limit 500
```

The API equivalent is protected by the same admin token:

```text
POST /admin/jobs/curate-relevance
```

`GET /talks` hides rejected candidates by default. Use `include_rejected=true` only for audit/debug views.

## Cloud Processing

Use `process-pending` to turn stored candidates into research-ready talks. It downloads audio, transcribes, summarizes, optionally indexes vectors, and records the run in `ingestion_runs`:

```powershell
python main.py job process-pending --company NVDA --limit 1 --transcription-provider faster_whisper --whisper-model-size base
```

To process one exact row:

```powershell
python main.py job process-pending --talk-id 12 --transcription-provider faster_whisper --whisper-model-size base
```

`process-pending` only processes `pending`, `error`, `downloading`, `transcribing`, and `summarizing` talks. It skips `ready` and `rejected` rows so false positives do not accidentally enter the research database.

The repository includes `.github/workflows/cloud-process.yml` for manual cloud processing on GitHub Actions. Configure this required secret:

```text
CEO_TALK_DATABASE_URL=<Render external Postgres URL with sslmode=require>
```

Optional secrets:

```text
OPENAI_API_KEY=<required only for OpenAI transcription or summaries>
QDRANT_URL=<Qdrant Cloud URL, optional>
QDRANT_API_KEY=<Qdrant API key, optional>
```

Run it from GitHub Actions:

```text
Actions -> Cloud Process Pending Talks -> Run workflow
company=NVDA
limit=1
transcription_provider=faster_whisper
whisper_model_size=base
summary_provider=heuristic
```

The first run downloads the Whisper model and can take longer. Later runs reuse the GitHub Actions model cache. Audio and local transcript files are temporary on the Actions runner; the durable system of record is Render Postgres. Persistent object storage for audio/transcript artifacts is a later production step.

## GitHub Actions Scheduler

The repository includes `.github/workflows/cloud-ingest.yml` as a no-worker fallback. It calls the public API and triggers metadata-only ingestion through:

```text
POST /admin/jobs/daily-ingest
```

After ingestion succeeds, the workflow also calls:

```text
POST /admin/jobs/curate-relevance
```

This means scheduled runs both discover new candidates and clean stale false positives from the default research view.

Set these GitHub Actions secrets:

```text
CEO_TALK_ADMIN_TOKEN=<same value as Render ADMIN_API_TOKEN>
CEO_TALK_API_BASE_URL=https://ceo-talk-monitor-api.onrender.com
```

Set this Render API service environment variable:

```text
ADMIN_API_TOKEN=<strong random token>
```

The scheduled workflow runs on weekdays and defaults to:

```text
source=youtube
company=<all config.yaml portfolio tickers>
limit=1
metadata_only=true
```

This keeps discovery automated without running audio download or Whisper inside the web API container.

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
ADMIN_API_TOKEN=
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
