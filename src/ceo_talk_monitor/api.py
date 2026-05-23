from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ceo_talk_monitor.compare import compare_company_topic, postgres_text_search
from ceo_talk_monitor.config import get_config
from ceo_talk_monitor.db import SessionLocal, get_session, init_db, upsert_config_companies
from ceo_talk_monitor.models import Company, Talk
from ceo_talk_monitor.vector_store import VectorStore


def create_app() -> FastAPI:
    app = FastAPI(title="Nasdaq Top 10 CEO Talk Monitor", version="0.1.0")

    @app.on_event("startup")
    def startup() -> None:
        config = get_config()
        init_db()
        with SessionLocal() as session:
            upsert_config_companies(session, config)

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
        limit: int = Query(default=50, le=200),
        session: Session = Depends(get_session),
    ) -> list[dict]:
        statement = select(Talk).options(selectinload(Talk.summary)).order_by(Talk.published_at.desc().nullslast(), Talk.id.desc())
        if company:
            statement = statement.where(Talk.company_ticker == company.upper())
        rows = session.scalars(statement.limit(limit)).all()
        return [_talk_payload(row, include_segments=False) for row in rows]

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
        vector_results: list[dict] = []
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


app = create_app()
