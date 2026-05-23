from __future__ import annotations

import re

from sqlalchemy import Text, and_, cast, or_
from sqlalchemy.orm import Session

from ceo_talk_monitor.models import Summary, Talk, TranscriptSegment


def compare_company_topic(session: Session, company: str, topic: str, limit: int = 10) -> dict:
    terms = _query_terms(topic)
    rows = (
        session.query(Talk, Summary)
        .join(Summary, Summary.talk_id == Talk.id)
        .outerjoin(TranscriptSegment, TranscriptSegment.talk_id == Talk.id)
        .filter(Talk.company_ticker == company.upper())
        .filter(_all_terms_filter(terms))
        .order_by(Talk.published_at.desc().nullslast(), Talk.id.desc())
        .all()
    )
    timeline = []
    seen: set[int] = set()
    for talk, summary in rows:
        if talk.id in seen:
            continue
        seen.add(talk.id)
        timeline.append(
            {
                "talk_id": talk.id,
                "published_at": talk.published_at.isoformat() if talk.published_at else None,
                "title": talk.title,
                "executive": talk.executive_name,
                "tone": summary.management_tone,
                "one_liner": summary.one_liner,
                "changes_vs_prior": summary.changes_vs_prior,
                "source_url": talk.source_url,
            }
        )
        if len(timeline) >= limit:
            break
    return {
        "company": company.upper(),
        "topic": topic,
        "count": len(timeline),
        "timeline": timeline,
    }


def postgres_text_search(session: Session, query: str, limit: int = 10) -> list[dict]:
    terms = _query_terms(query)
    rows = (
        session.query(Talk, Summary)
        .outerjoin(Summary, Summary.talk_id == Talk.id)
        .outerjoin(TranscriptSegment, TranscriptSegment.talk_id == Talk.id)
        .filter(_any_terms_filter(terms))
        .order_by(Talk.published_at.desc().nullslast(), Talk.id.desc())
        .all()
    )
    results = []
    seen: set[int] = set()
    for talk, summary in rows:
        if talk.id in seen:
            continue
        seen.add(talk.id)
        results.append(
            {
                "talk_id": talk.id,
                "company": talk.company_ticker,
                "title": talk.title,
                "executive": talk.executive_name,
                "published_at": talk.published_at.isoformat() if talk.published_at else None,
                "one_liner": summary.one_liner if summary else None,
                "source_url": talk.source_url,
            }
        )
        if len(results) >= limit:
            break
    return results


def _query_terms(query: str) -> list[str]:
    terms = [term for term in re.split(r"\W+", query) if len(term) >= 2]
    return terms or [query]


def _term_filter(term: str):
    pattern = f"%{term}%"
    return or_(
        Talk.title.ilike(pattern),
        Talk.description.ilike(pattern),
        Summary.one_liner.ilike(pattern),
        cast(Summary.core_topics, Text).ilike(pattern),
        cast(Summary.signals, Text).ilike(pattern),
        TranscriptSegment.text.ilike(pattern),
    )


def _any_terms_filter(terms: list[str]):
    return or_(*[_term_filter(term) for term in terms])


def _all_terms_filter(terms: list[str]):
    return and_(*[_term_filter(term) for term in terms])
