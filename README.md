# Nasdaq Top 10 CEO Talk Monitor

MVP system for tracking CEO/CFO/COO interviews from CNBC YouTube and selected podcast RSS feeds, then downloading audio, transcribing, summarizing, indexing, and exposing the talks through a CLI and FastAPI.

The initial tracking list is configured in `config.yaml` and can be updated without code changes.

## MVP Goal

Input `NVDA`, find CNBC YouTube videos related to Jensen Huang, download audio, transcribe, summarize, save to PostgreSQL, index in Qdrant, and query through API.

## Project Structure

```text
.
|-- config.yaml
|-- docker-compose.yml
|-- Dockerfile
|-- Dockerfile.api
|-- Dockerfile.worker
|-- main.py
|-- pyproject.toml
|-- requirements.txt
|-- requirements-api.txt
|-- requirements-worker.txt
|-- schema.sql
|-- .env.example
|-- apps/
|   `-- web/
|-- src/
|   `-- ceo_talk_monitor/
|       |-- api.py
|       |-- audio.py
|       |-- cli.py
|       |-- compare.py
|       |-- config.py
|       |-- db.py
|       |-- embeddings.py
|       |-- ingestion.py
|       |-- jobs.py
|       |-- models.py
|       |-- prompts.py
|       |-- relevance.py
|       |-- schemas.py
|       |-- summarizer.py
|       |-- transcript.py
|       |-- vector_store.py
|       `-- collectors/
|           |-- podcast.py
|           `-- youtube.py
`-- data/
    |-- audio/
    `-- transcripts/
```

## Quick Start

1. Copy environment settings:

```powershell
Copy-Item .env.example .env
```

2. Start services:

```powershell
docker compose up --build
```

3. Initialize database from config:

```powershell
docker compose run --rm app python main.py init-db
```

4. Ingest NVDA from YouTube:

```powershell
docker compose run --rm app python main.py ingest --source youtube --company NVDA
```

5. Query API:

```text
http://localhost:8000/companies
http://localhost:8000/talks?company=NVDA
http://localhost:8000/search?q=Jensen%20Huang%20supply%20constraint
```

## Cloud Deployment Direction

The recommended GitHub repository is:

```text
JasonYeh199/ceo-talk-monitor
```

Vercel hosts the research UI in `apps/web`. The FastAPI query API and long-running download/transcription/summarization worker should run in a separate container runtime. See:

- `docs/github_vercel_setup.md`
- `docs/vercel_architecture.md`
- `docs/backend_api_deployment.md`
- `docs/render_deployment.md`
- `docs/operations.md`

The first Vercel-ready research dashboard lives in `apps/web`.

GitHub Actions runs basic Python and Next.js build checks on each push to `main`.

### Vercel Import Settings

When importing this repository into Vercel, do not deploy the repository root as a FastAPI project. Use:

```text
Application Preset: Next.js
Root Directory: apps/web
Install Command: npm ci
Build Command: npm run build
Output Directory: .next
```

If Vercel shows `Application Preset: FastAPI` or errors with `Found main.py but it does not define a top-level`, the project root is still set to `./`. Click `Edit` next to Root Directory and change it to `apps/web`.

The repository also includes a root-level `vercel.json` fallback that builds `apps/web` from the repository root. Root Directory `apps/web` is still preferred because it keeps the Vercel project scoped to the dashboard.

If Vercel says `No Next.js version detected`, it is still reading the repository root. Redeploy the latest commit, or set Root Directory to `apps/web` so Vercel reads `apps/web/package.json`.

## Local Python Usage

Install Python 3.11+, FFmpeg, and dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run Postgres and Qdrant with Docker:

```powershell
docker compose up postgres qdrant
```

The compose file exposes Postgres on host port `5433` to avoid conflicts with an existing local Postgres on `5432`.

Then:

```powershell
python main.py init-db
python main.py ingest --source youtube --company NVDA
python main.py ingest --source podcast
python main.py daily
python main.py job daily-ingest --source youtube --company NVDA --limit 3 --metadata-only
python main.py process --company NVDA --limit 1
python main.py summarize --company NVDA --days 30
python main.py compare --company NVDA --topic "AI demand"
python main.py search "Jensen Huang supply constraint"
python main.py api
```

For cloud deployment, use `Dockerfile.api` for the public query API and `Dockerfile.worker` for long-running ingest/transcription jobs.

## CLI

```text
python main.py init-db
python main.py ingest --source youtube --company NVDA
python main.py ingest --source podcast
python main.py ingest --source all
python main.py daily
python main.py job daily-ingest --source all --limit 3
python main.py process --company NVDA --limit 1
python main.py summarize --company NVDA --days 30
python main.py compare --company NVDA --topic "AI demand"
python main.py search "Jensen Huang supply constraint"
python main.py api --host 0.0.0.0 --port 8000
```

## API

```text
GET /companies
GET /healthz
GET /readyz
GET /talks?company=NVDA
GET /talks/{id}
GET /search?q=AI+demand
GET /compare?company=NVDA&topic=AI+demand
GET /jobs
```

## Database Schema

Core tables:

- `companies`: ticker, company name, aliases.
- `executives`: company executives and roles from `config.yaml`.
- `talks`: media metadata, relevance score, processing status, audio/transcript paths.
- `transcript_segments`: timestamped transcript text, optional speaker labels.
- `summaries`: investment summary fields and raw JSON payload.
- `ingestion_runs`: operational history for scheduled ingestion jobs.

Embeddings are stored in Qdrant under the collection configured by `vector_store.collection_name`.

## Configuration

Update `config.yaml` to change tracked holdings, executives, RSS feeds, relevance threshold, model settings, or storage paths.

The sample `portfolio.source` block records the source URL and date for the initial QQQ/Nasdaq-100 tracking list. Refresh the holdings periodically from Invesco, Yahoo Finance, Schwab, or another trusted source, then update only config.

## Notes

- YouTube search and downloads use `yt-dlp`; FFmpeg is required for audio extraction.
- Transcription defaults to `faster-whisper`.
- Speaker diarization is left as a pluggable hook in MVP and disabled by default.
- If `OPENAI_API_KEY` is present and `summarization.provider` is set to `openai`, summaries use an LLM. Otherwise the system falls back to a deterministic extractive summary.
- Podcast ingest requires each RSS feed to expose an audio enclosure.
