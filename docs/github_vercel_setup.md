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
Set Root Directory to apps/web
```

Important: the repository root contains the Python CLI/API entrypoint `main.py`. If Vercel is left at root directory `./`, it may auto-select `FastAPI` and fail with:

```text
Found main.py but it does not define a top-level
```

That is expected for the wrong project root. The Vercel project should be the Next.js web app in `apps/web`, not the Python worker/API.

For the production architecture, Vercel should host the research UI. The FastAPI query API and heavy jobs such as `yt-dlp`, Whisper transcription, and embedding generation should run in container environments outside Vercel.

## Required Environment Variables

For Vercel UI:

```text
NEXT_PUBLIC_API_BASE_URL
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
FastAPI query API is available at a public HTTPS URL
Postgres and Qdrant are external managed services
Worker still runs locally or on a separate worker platform
```

This avoids forcing long-running transcription jobs into Vercel Functions.

## Vercel Project Settings

```text
Framework Preset: Next.js
Root Directory: apps/web
Build Command: npm run build
Install Command: npm ci
Output Directory: .next
```

If the import screen still shows `Application Preset: FastAPI`, manually change it to `Next.js` after setting Root Directory to `apps/web`.
