# GitHub and Vercel Setup

Target GitHub owner:

```text
JasonYeh199
```

Recommended repository:

```text
JasonYeh199/ceo-talk-monitor
```

## Important

Do not commit downloaded audio, generated transcripts, model caches, or `.env` files. These are ignored by `.gitignore`.

The GitHub repository should contain source code, config samples, docs, schema, and deployment files only.

## Create GitHub Repository

Create a new repository under:

```text
https://github.com/JasonYeh199
```

Recommended settings:

```text
Repository name: ceo-talk-monitor
Visibility: Private
Initialize with README: No
Add .gitignore: No
Add license: Decide later after source/data policy review
```

## Push Local Project

Run from the project root:

```powershell
git init
git branch -M main
git add .
git status
git commit -m "Initial MVP for CEO talk monitor"
git remote add origin https://github.com/JasonYeh199/ceo-talk-monitor.git
git push -u origin main
```

If Git asks for authentication, use GitHub's browser login flow or a personal access token with repository write permission.

## Connect to Vercel

In Vercel:

```text
Add New Project
Import Git Repository
Select JasonYeh199/ceo-talk-monitor
```

For the production architecture, Vercel should host the research UI and thin query API. Heavy jobs such as `yt-dlp`, Whisper transcription, and embedding generation should run in a worker environment outside Vercel.

## Required Environment Variables

For Vercel UI / thin API:

```text
DATABASE_URL
QDRANT_URL
OPENAI_API_KEY
OPENAI_SUMMARY_MODEL
APP_CONFIG_PATH
```

For worker runtime:

```text
DATABASE_URL
QDRANT_URL
OPENAI_API_KEY
OPENAI_SUMMARY_MODEL
HF_TOKEN
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY_ID
OBJECT_STORAGE_SECRET_ACCESS_KEY
```

## First Cloud Milestone

The first cloud milestone should be:

```text
GitHub repo connected to Vercel
Vercel serves a read-only research UI
Postgres and Qdrant are external managed services
Worker still runs locally or on a separate worker platform
```

This avoids forcing long-running transcription jobs into Vercel Functions.

