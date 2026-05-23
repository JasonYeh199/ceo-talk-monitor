from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ceo_talk_monitor.config import AppConfig
from ceo_talk_monitor.ingestion import IngestionPipeline
from ceo_talk_monitor.models import IngestionRun, Talk, utcnow
from ceo_talk_monitor.relevance import score_candidate
from ceo_talk_monitor.schemas import MediaCandidate

logger = logging.getLogger(__name__)

VALID_SOURCES = {"youtube", "podcast", "all"}
PROCESSABLE_STATUSES = ("pending", "error", "downloading", "transcribing", "summarizing")


def run_daily_ingest(
    session: Session,
    config: AppConfig,
    *,
    source: str = "all",
    company: str | None = None,
    limit: int | None = None,
    process: bool = True,
    lock_ttl_minutes: int = 180,
) -> IngestionRun:
    normalized_source = source.lower()
    if normalized_source not in VALID_SOURCES:
        raise ValueError(f"Unsupported source: {source}")

    normalized_company = company.upper() if company else None
    parameters = {
        "source": normalized_source,
        "company": normalized_company,
        "limit": limit,
        "process": process,
        "lock_ttl_minutes": lock_ttl_minutes,
    }

    active_run = _find_active_run(session, "daily-ingest", lock_ttl_minutes)
    if active_run is not None:
        return _record_skipped_run(
            session,
            "daily-ingest",
            parameters,
            normalized_source,
            normalized_company,
            f"Skipped because ingestion run {active_run.id} is still running.",
            {"active_run_id": active_run.id, "active_started_at": active_run.started_at.isoformat()},
        )

    run = IngestionRun(
        job_name="daily-ingest",
        status="running",
        source=normalized_source,
        company_ticker=normalized_company,
        parameters=parameters,
        metrics={},
        started_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        pipeline = IngestionPipeline(config, session)
        pipeline.bootstrap()
        metrics = _run_pipeline(pipeline, config, normalized_source, normalized_company, limit, process)
        run.status = "succeeded"
        run.metrics = metrics
        run.exit_code = 0
        run.error_message = None
    except Exception as exc:
        logger.exception("Daily ingestion job failed")
        session.rollback()
        run = session.get(IngestionRun, run.id) or run
        run.status = "failed"
        run.metrics = run.metrics or {}
        run.error_message = str(exc)
        run.exit_code = 1
    finally:
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)

    return run


def _run_pipeline(
    pipeline: IngestionPipeline,
    config: AppConfig,
    source: str,
    company: str | None,
    limit: int | None,
    process: bool,
) -> dict:
    metrics: dict = {
        "accepted_total": 0,
        "youtube": {},
        "podcast": {"accepted": 0},
        "process": process,
    }

    if source in ("youtube", "all"):
        companies = [company] if company else config.portfolio.tickers
        for ticker in companies:
            talks = pipeline.ingest_youtube(ticker, limit=limit, process=process)
            metrics["youtube"][ticker] = {
                "accepted": len(talks),
                "ready": sum(1 for talk in talks if talk.status == "ready"),
                "errors": sum(1 for talk in talks if talk.status == "error"),
            }
            metrics["accepted_total"] += len(talks)

    if source in ("podcast", "all"):
        talks = pipeline.ingest_podcasts(company, limit=limit, process=process)
        metrics["podcast"] = {
            "accepted": len(talks),
            "ready": sum(1 for talk in talks if talk.status == "ready"),
            "errors": sum(1 for talk in talks if talk.status == "error"),
        }
        metrics["accepted_total"] += len(talks)

    return metrics


def _find_active_run(session: Session, job_name: str, lock_ttl_minutes: int) -> IngestionRun | None:
    if lock_ttl_minutes <= 0:
        return None
    cutoff = utcnow() - timedelta(minutes=lock_ttl_minutes)
    return session.scalar(
        select(IngestionRun)
        .where(IngestionRun.job_name == job_name)
        .where(IngestionRun.status == "running")
        .where(IngestionRun.started_at >= cutoff)
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )


def _record_skipped_run(
    session: Session,
    job_name: str,
    parameters: dict,
    source: str,
    company: str | None,
    message: str,
    metrics: dict,
) -> IngestionRun:
    now = utcnow()
    run = IngestionRun(
        job_name=job_name,
        status="skipped",
        source=source,
        company_ticker=company,
        started_at=now,
        finished_at=now,
        parameters=parameters,
        metrics=metrics,
        error_message=message,
        exit_code=0,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def curate_relevance(
    session: Session,
    config: AppConfig,
    *,
    company: str | None = None,
    limit: int = 500,
    statuses: tuple[str, ...] = ("pending",),
) -> IngestionRun:
    normalized_company = company.upper() if company else None
    parameters = {
        "company": normalized_company,
        "limit": limit,
        "statuses": list(statuses),
    }
    run = IngestionRun(
        job_name="curate-relevance",
        status="running",
        source="database",
        company_ticker=normalized_company,
        parameters=parameters,
        metrics={},
        started_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        metrics = _curate_relevance_rows(session, config, normalized_company, limit, statuses)
        run.status = "succeeded"
        run.metrics = metrics
        run.exit_code = 0
        run.error_message = None
    except Exception as exc:
        logger.exception("Relevance curation job failed")
        session.rollback()
        run = session.get(IngestionRun, run.id) or run
        run.status = "failed"
        run.metrics = run.metrics or {}
        run.error_message = str(exc)
        run.exit_code = 1
    finally:
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)

    return run


def _curate_relevance_rows(
    session: Session,
    config: AppConfig,
    company: str | None,
    limit: int,
    statuses: tuple[str, ...],
) -> dict:
    statement = select(Talk).where(Talk.status.in_(statuses))
    if company:
        statement = statement.where(Talk.company_ticker == company)
    statement = statement.order_by(Talk.id.desc()).limit(limit)

    checked = 0
    kept = 0
    rejected = 0
    by_company: dict[str, dict[str, int]] = {}

    for talk in session.scalars(statement):
        company_metrics = by_company.setdefault(talk.company_ticker, {"checked": 0, "kept": 0, "rejected": 0})
        company_cfg = config.company_by_ticker(talk.company_ticker)
        result = score_candidate(
            MediaCandidate(
                source=talk.source,
                title=talk.title,
                url=talk.source_url,
                published_at=talk.published_at,
                duration_seconds=talk.duration_seconds,
                description=talk.description,
                external_id=talk.external_id,
            ),
            company_cfg,
            config.relevance,
        )

        checked += 1
        company_metrics["checked"] += 1
        talk.relevance_score = result.score
        talk.relevance_reasons = result.reasons
        talk.executive_name = result.executive_name
        talk.executive_role = result.executive_role

        if result.passed:
            kept += 1
            company_metrics["kept"] += 1
            if talk.status == "rejected":
                talk.status = "pending"
                talk.error_message = None
        else:
            rejected += 1
            company_metrics["rejected"] += 1
            talk.status = "rejected"
            talk.error_message = "Rejected by relevance curation"

    session.commit()
    return {
        "checked": checked,
        "kept": kept,
        "rejected": rejected,
        "by_company": by_company,
    }


def run_process_pending(
    session: Session,
    config: AppConfig,
    *,
    talk_id: int | None = None,
    company: str | None = None,
    limit: int = 1,
    statuses: tuple[str, ...] = PROCESSABLE_STATUSES,
    lock_ttl_minutes: int = 720,
) -> IngestionRun:
    normalized_company = company.upper() if company else None
    parameters = {
        "talk_id": talk_id,
        "company": normalized_company,
        "limit": limit,
        "statuses": list(statuses),
        "lock_ttl_minutes": lock_ttl_minutes,
    }

    active_run = _find_active_run(session, "process-pending", lock_ttl_minutes)
    if active_run is not None:
        return _record_skipped_run(
            session,
            "process-pending",
            parameters,
            "database",
            normalized_company,
            f"Skipped because processing run {active_run.id} is still running.",
            {"active_run_id": active_run.id, "active_started_at": active_run.started_at.isoformat()},
        )

    run = IngestionRun(
        job_name="process-pending",
        status="running",
        source="database",
        company_ticker=normalized_company,
        parameters=parameters,
        metrics={},
        started_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        pipeline = IngestionPipeline(config, session)
        pipeline.bootstrap()
        metrics = _process_pending_rows(session, pipeline, talk_id, normalized_company, limit, statuses)
        run.status = "succeeded"
        run.metrics = metrics
        run.exit_code = 0
        run.error_message = None
    except Exception as exc:
        logger.exception("Pending processing job failed")
        session.rollback()
        run = session.get(IngestionRun, run.id) or run
        run.status = "failed"
        run.metrics = run.metrics or {}
        run.error_message = str(exc)
        run.exit_code = 1
    finally:
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)

    return run


def _process_pending_rows(
    session: Session,
    pipeline: IngestionPipeline,
    talk_id: int | None,
    company: str | None,
    limit: int,
    statuses: tuple[str, ...],
) -> dict:
    if talk_id is not None:
        talks = [session.get(Talk, talk_id)]
    else:
        statement = select(Talk).where(Talk.status.in_(statuses))
        if company:
            statement = statement.where(Talk.company_ticker == company)
        statement = statement.order_by(Talk.published_at.desc().nullslast(), Talk.id.desc()).limit(limit)
        talks = list(session.scalars(statement))

    processed = 0
    ready = 0
    errors = 0
    skipped = 0
    results: list[dict] = []
    by_company: dict[str, dict[str, int]] = {}

    for talk in talks:
        if talk is None:
            skipped += 1
            results.append({"talk_id": talk_id, "status": "missing"})
            continue
        if talk.status == "rejected":
            skipped += 1
            results.append({"talk_id": talk.id, "status": "rejected"})
            continue
        if talk.status == "ready":
            skipped += 1
            results.append({"talk_id": talk.id, "status": "ready"})
            continue

        company_metrics = by_company.setdefault(talk.company_ticker, {"processed": 0, "ready": 0, "errors": 0})
        before_status = talk.status
        pipeline.process_talk(talk)
        processed += 1
        company_metrics["processed"] += 1
        if talk.status == "ready":
            ready += 1
            company_metrics["ready"] += 1
        elif talk.status == "error":
            errors += 1
            company_metrics["errors"] += 1

        results.append(
            {
                "talk_id": talk.id,
                "company": talk.company_ticker,
                "title": talk.title,
                "before_status": before_status,
                "after_status": talk.status,
                "error_message": talk.error_message,
            }
        )

    session.commit()
    return {
        "processed": processed,
        "ready": ready,
        "errors": errors,
        "skipped": skipped,
        "results": results,
        "by_company": by_company,
    }
