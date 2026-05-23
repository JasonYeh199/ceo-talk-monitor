from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ceo_talk_monitor.audio import download_url_audio, download_youtube_audio, safe_slug
from ceo_talk_monitor.collectors.podcast import PodcastCollector
from ceo_talk_monitor.collectors.youtube import YoutubeCollector
from ceo_talk_monitor.config import AppConfig, ensure_storage_dirs, get_settings
from ceo_talk_monitor.db import init_db, upsert_config_companies
from ceo_talk_monitor.models import Company, Summary, Talk, TranscriptSegment
from ceo_talk_monitor.relevance import score_candidate
from ceo_talk_monitor.schemas import MediaCandidate, RelevanceResult, SummaryPayload, TranscriptPayload
from ceo_talk_monitor.summarizer import Summarizer
from ceo_talk_monitor.transcript import TranscriptProcessor
from ceo_talk_monitor.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, config: AppConfig, session: Session):
        self.config = config
        self.session = session
        self.youtube = YoutubeCollector(config.sources.youtube)
        self.podcast = PodcastCollector()
        self.transcriber = TranscriptProcessor(config.transcription)
        self.summarizer = Summarizer(config.summarization)
        self.vector_store = VectorStore(config.vector_store)

    def bootstrap(self) -> None:
        ensure_storage_dirs(self.config)
        init_db()
        upsert_config_companies(self.session, self.config)

    def ingest_youtube(self, company_ticker: str, limit: int | None = None, process: bool = True) -> list[Talk]:
        company_cfg = self.config.company_by_ticker(company_ticker)
        accepted: list[Talk] = []
        for candidate in self.youtube.search_company(company_cfg):
            relevance = score_candidate(candidate, company_cfg, self.config.relevance)
            if not relevance.passed:
                logger.info("Skipping %s score=%s reasons=%s", candidate.title, relevance.score, relevance.reasons)
                continue
            talk = self._upsert_candidate(candidate, relevance)
            accepted.append(talk)
            if process:
                self.process_talk(talk, candidate)
            if limit and len(accepted) >= limit:
                break
        return accepted

    def ingest_podcasts(self, company_ticker: str | None = None, limit: int | None = None, process: bool = True) -> list[Talk]:
        companies = [self.config.company_by_ticker(company_ticker)] if company_ticker else self.config.tracked_companies()
        accepted: list[Talk] = []
        for feed in self.config.sources.podcasts.feeds:
            for candidate in self.podcast.fetch_feed(feed, self.config.sources.podcasts.max_entries_per_feed):
                best: RelevanceResult | None = None
                for company_cfg in companies:
                    relevance = score_candidate(candidate, company_cfg, self.config.relevance)
                    if relevance.passed and (best is None or relevance.score > best.score):
                        best = relevance
                if best is None:
                    continue
                talk = self._upsert_candidate(candidate, best)
                accepted.append(talk)
                if process:
                    self.process_talk(talk, candidate)
                if limit and len(accepted) >= limit:
                    return accepted
        return accepted

    def process_talk(self, talk: Talk, candidate: MediaCandidate | None = None) -> Talk:
        try:
            if not talk.audio_path:
                talk.status = "downloading"
                self.session.commit()
                talk.audio_path = str(self._download_audio(talk, candidate))
                self.session.commit()

            if not talk.transcript_segments:
                talk.status = "transcribing"
                self.session.commit()
                transcript = self.transcriber.transcribe(talk.audio_path)
                self._save_transcript(talk, transcript)
            else:
                transcript = TranscriptPayload(
                    segments=[
                        {
                            "start_seconds": segment.start_seconds,
                            "end_seconds": segment.end_seconds,
                            "text": segment.text,
                            "speaker": segment.speaker,
                        }
                        for segment in talk.transcript_segments
                    ]
                )

            talk.status = "summarizing"
            self.session.commit()
            summary = self.summarizer.summarize(
                title=talk.title,
                company_ticker=talk.company_ticker,
                executive_name=talk.executive_name,
                executive_role=talk.executive_role,
                source_url=talk.source_url,
                transcript=transcript,
            )
            self._save_summary(talk, summary)
            self._index_talk(talk, transcript, summary)
            talk.status = "ready"
            talk.error_message = None
            self.session.commit()
            return talk
        except Exception as exc:
            logger.exception("Failed processing talk %s", talk.id)
            talk.status = "error"
            talk.error_message = str(exc)
            self.session.commit()
            return talk

    def summarize_existing(self, company_ticker: str, days: int = 30) -> list[Summary]:
        talks = self._recent_talks(company_ticker, days)
        summaries: list[Summary] = []
        for talk in talks:
            if talk.transcript_segments:
                transcript = TranscriptPayload(
                    segments=[
                        {
                            "start_seconds": segment.start_seconds,
                            "end_seconds": segment.end_seconds,
                            "text": segment.text,
                            "speaker": segment.speaker,
                        }
                        for segment in talk.transcript_segments
                    ]
                )
                summary_payload = self.summarizer.summarize(
                    title=talk.title,
                    company_ticker=talk.company_ticker,
                    executive_name=talk.executive_name,
                    executive_role=talk.executive_role,
                    source_url=talk.source_url,
                    transcript=transcript,
                )
                summaries.append(self._save_summary(talk, summary_payload))
        self.session.commit()
        return summaries

    def _upsert_candidate(self, candidate: MediaCandidate, relevance: RelevanceResult) -> Talk:
        existing = self.session.scalar(select(Talk).where(Talk.source_url == candidate.url))
        company = self.session.scalar(select(Company).where(Company.ticker == relevance.company_ticker))
        if existing:
            existing.relevance_score = relevance.score
            existing.relevance_reasons = relevance.reasons
            existing.executive_name = relevance.executive_name
            existing.executive_role = relevance.executive_role
            self.session.commit()
            return existing
        talk = Talk(
            source=candidate.source,
            source_url=candidate.url,
            external_id=candidate.external_id,
            title=candidate.title,
            description=candidate.description,
            published_at=candidate.published_at,
            duration_seconds=candidate.duration_seconds,
            company_id=company.id if company else None,
            company_ticker=relevance.company_ticker,
            executive_name=relevance.executive_name,
            executive_role=relevance.executive_role,
            relevance_score=relevance.score,
            relevance_reasons=relevance.reasons,
            status="pending",
        )
        self.session.add(talk)
        self.session.commit()
        self.session.refresh(talk)
        return talk

    def _download_audio(self, talk: Talk, candidate: MediaCandidate | None) -> Path:
        stem = f"{talk.company_ticker}-{talk.id}-{safe_slug(talk.title, 48)}"
        company_dir = Path(self.config.storage.audio_dir) / talk.company_ticker
        if talk.source == "youtube":
            return download_youtube_audio(talk.source_url, company_dir, stem)
        audio_url = candidate.audio_url if candidate and candidate.audio_url else talk.source_url
        return download_url_audio(audio_url, company_dir, stem)

    def _save_transcript(self, talk: Talk, transcript: TranscriptPayload) -> None:
        stem = f"{talk.company_ticker}-{talk.id}"
        talk.transcript_path = str(
            self.transcriber.write_transcript(transcript, Path(self.config.storage.transcript_dir) / talk.company_ticker, stem)
        )
        self.session.execute(delete(TranscriptSegment).where(TranscriptSegment.talk_id == talk.id))
        for segment in transcript.segments:
            self.session.add(
                TranscriptSegment(
                    talk_id=talk.id,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    speaker=segment.speaker,
                    text=segment.text,
                )
            )
        self.session.commit()

    def _save_summary(self, talk: Talk, payload: SummaryPayload) -> Summary:
        summary = self.session.scalar(select(Summary).where(Summary.talk_id == talk.id))
        if summary is None:
            summary = Summary(talk_id=talk.id, one_liner=payload.one_liner, management_tone=payload.management_tone)
            self.session.add(summary)
        summary.one_liner = payload.one_liner
        summary.management_tone = payload.management_tone
        summary.core_topics = payload.core_topics
        summary.signals = payload.signals
        summary.quotes = payload.quotes
        summary.changes_vs_prior = payload.changes_vs_prior
        summary.investable_hypotheses = payload.investable_hypotheses
        summary.risks = payload.risks
        summary.source_url = payload.source_url
        summary.raw_summary = payload.raw
        self.session.commit()
        self.session.refresh(summary)
        return summary

    def _index_talk(self, talk: Talk, transcript: TranscriptPayload, summary: SummaryPayload) -> None:
        if not get_settings().qdrant_url.strip():
            return
        text = "\n".join([talk.title, summary.one_liner, transcript.text[:20000]])
        payload = {
            "talk_id": talk.id,
            "company": talk.company_ticker,
            "executive": talk.executive_name,
            "role": talk.executive_role,
            "title": talk.title,
            "source_url": talk.source_url,
            "published_at": talk.published_at.isoformat() if talk.published_at else None,
        }
        try:
            self.vector_store.upsert_talk(talk.id, text, payload)
        except Exception:
            logger.exception("Vector indexing failed for talk %s", talk.id)

    def _recent_talks(self, company_ticker: str, days: int) -> list[Talk]:
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(days=days)
        return list(
            self.session.scalars(
                select(Talk)
                .where(Talk.company_ticker == company_ticker.upper())
                .where(or_(Talk.published_at.is_(None), Talk.published_at >= since))
                .order_by(Talk.published_at.desc().nullslast())
            )
        )
