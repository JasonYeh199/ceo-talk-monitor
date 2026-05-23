from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ceo_talk_monitor.db import engine as local_engine
from ceo_talk_monitor.db import normalize_database_url
from ceo_talk_monitor.models import Base, Company, Executive, Summary, Talk, TranscriptSegment


def ensure_sslmode(database_url: str) -> str:
    parsed = urlparse(database_url)
    if "render.com" not in (parsed.hostname or "") or "sslmode=" in parsed.query:
        return database_url
    query = dict(parse_qsl(parsed.query))
    query["sslmode"] = "require"
    return urlunparse(parsed._replace(query=urlencode(query)))


def main() -> None:
    cloud_url = os.environ.get("CLOUD_DATABASE_URL")
    if not cloud_url:
        raise SystemExit("CLOUD_DATABASE_URL is required")

    cloud_engine = create_engine(normalize_database_url(ensure_sslmode(cloud_url)), pool_pre_ping=True)
    Base.metadata.create_all(cloud_engine)

    with Session(local_engine) as source, Session(cloud_engine) as target:
        company_id_map: dict[int, int] = {}
        for source_company in source.scalars(select(Company).order_by(Company.id)):
            target_company = target.scalar(select(Company).where(Company.ticker == source_company.ticker))
            if target_company is None:
                target_company = Company(
                    ticker=source_company.ticker,
                    name=source_company.name,
                    aliases=source_company.aliases,
                )
                target.add(target_company)
                target.flush()
            else:
                target_company.name = source_company.name
                target_company.aliases = source_company.aliases
            company_id_map[source_company.id] = target_company.id

            existing_execs = {
                (executive.name, executive.role): executive for executive in target_company.executives
            }
            for source_executive in source_company.executives:
                key = (source_executive.name, source_executive.role)
                target_executive = existing_execs.get(key)
                if target_executive is None:
                    target.add(
                        Executive(
                            company_id=target_company.id,
                            name=source_executive.name,
                            role=source_executive.role,
                            aliases=source_executive.aliases,
                        )
                    )
                else:
                    target_executive.aliases = source_executive.aliases

        target.flush()

        talk_id_map: dict[int, int] = {}
        source_talks = source.scalars(select(Talk).order_by(Talk.id)).all()
        for source_talk in source_talks:
            target_talk = target.scalar(select(Talk).where(Talk.source_url == source_talk.source_url))
            values = {
                "source": source_talk.source,
                "external_id": source_talk.external_id,
                "title": source_talk.title,
                "description": source_talk.description,
                "published_at": source_talk.published_at,
                "duration_seconds": source_talk.duration_seconds,
                "company_id": company_id_map.get(source_talk.company_id) if source_talk.company_id else None,
                "company_ticker": source_talk.company_ticker,
                "executive_name": source_talk.executive_name,
                "executive_role": source_talk.executive_role,
                "relevance_score": source_talk.relevance_score,
                "relevance_reasons": source_talk.relevance_reasons,
                "audio_path": source_talk.audio_path,
                "transcript_path": source_talk.transcript_path,
                "status": source_talk.status,
                "error_message": source_talk.error_message,
            }
            if target_talk is None:
                target_talk = Talk(source_url=source_talk.source_url, **values)
                target.add(target_talk)
                target.flush()
            else:
                for key, value in values.items():
                    setattr(target_talk, key, value)
            talk_id_map[source_talk.id] = target_talk.id

            target.query(TranscriptSegment).where(TranscriptSegment.talk_id == target_talk.id).delete()
            for segment in source_talk.transcript_segments:
                target.add(
                    TranscriptSegment(
                        talk_id=target_talk.id,
                        start_seconds=segment.start_seconds,
                        end_seconds=segment.end_seconds,
                        speaker=segment.speaker,
                        text=segment.text,
                    )
                )

            if source_talk.summary:
                target_summary = target.scalar(select(Summary).where(Summary.talk_id == target_talk.id))
                summary_values = {
                    "one_liner": source_talk.summary.one_liner,
                    "management_tone": source_talk.summary.management_tone,
                    "core_topics": source_talk.summary.core_topics,
                    "signals": source_talk.summary.signals,
                    "quotes": source_talk.summary.quotes,
                    "changes_vs_prior": source_talk.summary.changes_vs_prior,
                    "investable_hypotheses": source_talk.summary.investable_hypotheses,
                    "risks": source_talk.summary.risks,
                    "source_url": source_talk.summary.source_url,
                    "raw_summary": source_talk.summary.raw_summary,
                }
                if target_summary is None:
                    target.add(Summary(talk_id=target_talk.id, **summary_values))
                else:
                    for key, value in summary_values.items():
                        setattr(target_summary, key, value)

        target.commit()

    print(f"Synced {len(company_id_map)} companies and {len(talk_id_map)} talks to cloud database.")


if __name__ == "__main__":
    main()
