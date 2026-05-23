from __future__ import annotations

from secrets import compare_digest

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from ceo_talk_monitor.compare import compare_company_topic, postgres_text_search
from ceo_talk_monitor.config import get_config, get_settings
from ceo_talk_monitor.db import SessionLocal, get_session, init_db, upsert_config_companies
from ceo_talk_monitor.jobs import VALID_SOURCES, curate_relevance, run_daily_ingest
from ceo_talk_monitor.models import Company, IngestionRun, Talk
from ceo_talk_monitor.vector_store import VectorStore


def create_app() -> FastAPI:
    app = FastAPI(title="Nasdaq Top 10 CEO Talk Monitor", version="0.1.0")

    @app.on_event("startup")
    def startup() -> None:
        config = get_config()
        init_db()
        with SessionLocal() as session:
            upsert_config_companies(session, config)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict:
        try:
            config = get_config()
            settings = get_settings()
            with SessionLocal() as session:
                session.execute(text("select 1"))
            return {
                "status": "ready",
                "companies": len(config.companies),
                "tracked_tickers": config.portfolio.tickers,
                "qdrant_configured": bool(settings.qdrant_url.strip()),
            }
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/companies")
    def companies(session: Session = Depends(get_session)) -> list[dict]:
        rows = session.scalars(select(Company).order_by(Company.ticker)).all()
        return [
            {
                "ticker": row.ticker,
                "name": row.name,
                "aliases": row.aliases,
                "executives": [
                    {"name": executive.name, "role": executive.role, "aliases": executive.aliases}
                    for executive in row.executives
                ],
            }
            for row in rows
        ]

    @app.get("/talks")
    def talks(
        company: str | None = None,
        include_rejected: bool = False,
        limit: int = Query(default=50, le=200),
        session: Session = Depends(get_session),
    ) -> list[dict]:
        statement = select(Talk).options(selectinload(Talk.summary)).order_by(Talk.published_at.desc().nullslast(), Talk.id.desc())
        if company:
            statement = statement.where(Talk.company_ticker == company.upper())
        if not include_rejected:
            statement = statement.where(Talk.status != "rejected")
        rows = session.scalars(statement.limit(limit)).all()
        return [_talk_payload(row, include_segments=False) for row in rows]

    @app.get("/jobs")
    def jobs(
        status: str | None = None,
        limit: int = Query(default=10, le=50),
        session: Session = Depends(get_session),
    ) -> list[dict]:
        statement = select(IngestionRun).order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
        if status:
            statement = statement.where(IngestionRun.status == status)
        rows = session.scalars(statement.limit(limit)).all()
        return [_job_payload(row) for row in rows]

    @app.post("/admin/jobs/daily-ingest")
    def trigger_daily_ingest(
        source: str = Query(default="youtube"),
        company: str | None = None,
        limit: int = Query(default=1, ge=1, le=10),
        metadata_only: bool = True,
        lock_ttl_minutes: int = Query(default=180, ge=0, le=1440),
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    ) -> dict:
        _require_admin_token(x_admin_token)
        normalized_source = source.lower()
        if normalized_source not in VALID_SOURCES:
            raise HTTPException(status_code=400, detail=f"Unsupported source: {source}")
        if not metadata_only:
            raise HTTPException(status_code=400, detail="Cloud admin trigger only supports metadata_only=true")

        config = get_config()
        if company:
            try:
                config.company_by_ticker(company)
            except KeyError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        with SessionLocal() as session:
            run = run_daily_ingest(
                session,
                config,
                source=normalized_source,
                company=company,
                limit=limit,
                process=False,
                lock_ttl_minutes=lock_ttl_minutes,
            )
            return _job_payload(run)

    @app.post("/admin/jobs/curate-relevance")
    def trigger_relevance_curation(
        company: str | None = None,
        limit: int = Query(default=500, ge=1, le=1000),
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    ) -> dict:
        _require_admin_token(x_admin_token)
        config = get_config()
        if company:
            try:
                config.company_by_ticker(company)
            except KeyError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        with SessionLocal() as session:
            run = curate_relevance(session, config, company=company, limit=limit)
            return _job_payload(run)

    @app.get("/talks/{talk_id}")
    def talk_detail(talk_id: int, session: Session = Depends(get_session)) -> dict:
        talk = session.scalar(
            select(Talk)
            .where(Talk.id == talk_id)
            .options(selectinload(Talk.transcript_segments), selectinload(Talk.summary))
        )
        if talk is None:
            raise HTTPException(status_code=404, detail="Talk not found")
        return _talk_payload(talk, include_segments=True)

    @app.get("/search")
    def search(q: str, limit: int = Query(default=10, le=50), session: Session = Depends(get_session)) -> dict:
        config = get_config()
        settings = get_settings()
        vector_results: list[dict] = []
        if settings.qdrant_url.strip():
            try:
                vector_results = VectorStore(config.vector_store).search(q, limit=limit)
            except Exception:
                vector_results = []
        text_results = postgres_text_search(session, q, limit=limit)
        return {"query": q, "vector_results": vector_results, "text_results": text_results}

    @app.get("/compare")
    def compare(company: str, topic: str, limit: int = Query(default=10, le=50), session: Session = Depends(get_session)) -> dict:
        return compare_company_topic(session, company, topic, limit=limit)

    return app


def _talk_payload(talk: Talk, include_segments: bool) -> dict:
    payload = {
        "id": talk.id,
        "source": talk.source,
        "source_url": talk.source_url,
        "title": talk.title,
        "published_at": talk.published_at.isoformat() if talk.published_at else None,
        "duration_seconds": talk.duration_seconds,
        "company": talk.company_ticker,
        "executive": talk.executive_name,
        "role": talk.executive_role,
        "relevance_score": talk.relevance_score,
        "status": talk.status,
        "audio_path": talk.audio_path,
        "transcript_path": talk.transcript_path,
        "summary": None,
    }
    if talk.summary:
        payload["summary"] = {
            "one_liner": talk.summary.one_liner,
            "management_tone": talk.summary.management_tone,
            "core_topics": talk.summary.core_topics,
            "signals": talk.summary.signals,
            "quotes": talk.summary.quotes,
            "changes_vs_prior": talk.summary.changes_vs_prior,
            "investable_hypotheses": talk.summary.investable_hypotheses,
            "risks": talk.summary.risks,
        }
    if include_segments:
        payload["transcript_segments"] = [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "speaker": segment.speaker,
                "text": segment.text,
            }
            for segment in talk.transcript_segments
        ]
    return payload


def _job_payload(run: IngestionRun) -> dict:
    duration_seconds = None
    if run.finished_at:
        duration_seconds = max(0.0, (run.finished_at - run.started_at).total_seconds())
    return {
        "id": run.id,
        "job_name": run.job_name,
        "status": run.status,
        "source": run.source,
        "company": run.company_ticker,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": duration_seconds,
        "parameters": run.parameters,
        "metrics": run.metrics,
        "error_message": run.error_message,
        "exit_code": run.exit_code,
    }


def _require_admin_token(provided_token: str | None) -> None:
    expected_token = get_settings().admin_api_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="ADMIN_API_TOKEN is not configured")
    if not provided_token or not compare_digest(provided_token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")


app = create_app()
