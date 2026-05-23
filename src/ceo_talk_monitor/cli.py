from __future__ import annotations

import argparse
import logging
from pprint import pprint

from ceo_talk_monitor.compare import compare_company_topic, postgres_text_search
from ceo_talk_monitor.config import get_config, get_settings
from ceo_talk_monitor.db import SessionLocal, init_db, upsert_config_companies
from ceo_talk_monitor.ingestion import IngestionPipeline
from ceo_talk_monitor.jobs import curate_relevance, run_daily_ingest
from ceo_talk_monitor.models import Talk
from ceo_talk_monitor.vector_store import VectorStore
from sqlalchemy import select


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nasdaq Top 10 CEO Talk Monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create tables and load companies from config.yaml")

    ingest = subparsers.add_parser("ingest", help="Ingest YouTube or podcast sources")
    ingest.add_argument("--source", choices=["youtube", "podcast", "all"], required=True)
    ingest.add_argument("--company", help="Ticker, for example NVDA")
    ingest.add_argument("--limit", type=int, default=None)
    ingest.add_argument("--metadata-only", action="store_true", help="Save metadata without audio/transcript/summary processing")

    daily = subparsers.add_parser("daily", help="Run the daily check across configured sources")
    daily.add_argument("--company", help="Optional ticker to limit the daily check")
    daily.add_argument("--limit", type=int, default=None)
    daily.add_argument("--metadata-only", action="store_true")

    process = subparsers.add_parser("process", help="Process pending talks already stored in the database")
    process.add_argument("--talk-id", type=int, help="Process one specific talk id")
    process.add_argument("--company", help="Optional ticker filter for pending talks")
    process.add_argument("--limit", type=int, default=1)

    job = subparsers.add_parser("job", help="Run an operational job with persisted run history")
    job.add_argument("name", choices=["daily-ingest", "curate-relevance"])
    job.add_argument("--source", choices=["youtube", "podcast", "all"], default="all")
    job.add_argument("--company", help="Optional ticker to limit the job")
    job.add_argument("--limit", type=int, default=None)
    job.add_argument("--metadata-only", action="store_true", help="Save metadata without audio/transcript/summary processing")
    job.add_argument("--lock-ttl-minutes", type=int, default=180)

    summarize = subparsers.add_parser("summarize", help="Regenerate summaries for recent talks")
    summarize.add_argument("--company", required=True)
    summarize.add_argument("--days", type=int, default=30)

    compare = subparsers.add_parser("compare", help="Compare a company topic across talks")
    compare.add_argument("--company", required=True)
    compare.add_argument("--topic", required=True)
    compare.add_argument("--limit", type=int, default=10)

    search = subparsers.add_parser("search", help="Search transcripts and summaries")
    search.add_argument("query", nargs="+")
    search.add_argument("--limit", type=int, default=10)

    api = subparsers.add_parser("api", help="Run FastAPI server")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)

    return parser


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    args = build_parser().parse_args()

    if args.command == "api":
        import uvicorn

        uvicorn.run("ceo_talk_monitor.api:app", host=args.host, port=args.port, reload=False)
        return

    config = get_config()
    init_db()

    with SessionLocal() as session:
        upsert_config_companies(session, config)
        pipeline = IngestionPipeline(config, session)
        pipeline.bootstrap()

        if args.command == "init-db":
            print("Database initialized and companies loaded from config.yaml.")
            return

        if args.command == "ingest":
            process = not args.metadata_only
            if args.source in ("youtube", "all"):
                companies = [args.company] if args.company else config.portfolio.tickers
                for ticker in companies:
                    talks = pipeline.ingest_youtube(ticker, limit=args.limit, process=process)
                    print(f"YouTube {ticker}: accepted {len(talks)} talk(s)")
            if args.source in ("podcast", "all"):
                talks = pipeline.ingest_podcasts(args.company, limit=args.limit, process=process)
                print(f"Podcast: accepted {len(talks)} talk(s)")
            return

        if args.command == "daily":
            process = not args.metadata_only
            companies = [args.company] if args.company else config.portfolio.tickers
            for ticker in companies:
                talks = pipeline.ingest_youtube(ticker, limit=args.limit, process=process)
                print(f"YouTube {ticker}: accepted {len(talks)} talk(s)")
            talks = pipeline.ingest_podcasts(args.company, limit=args.limit, process=process)
            print(f"Podcast: accepted {len(talks)} talk(s)")
            return

        if args.command == "process":
            if args.talk_id:
                talks = [session.get(Talk, args.talk_id)]
            else:
                statement = select(Talk).where(Talk.status != "ready").order_by(Talk.id)
                if args.company:
                    statement = statement.where(Talk.company_ticker == args.company.upper())
                talks = list(session.scalars(statement.limit(args.limit)))
            processed = 0
            for talk in talks:
                if talk is None:
                    continue
                pipeline.process_talk(talk)
                print(f"[talk {talk.id}] {talk.status}: {talk.title}")
                processed += 1
            print(f"Processed {processed} talk(s)")
            return

        if args.command == "job":
            if args.name == "daily-ingest":
                run = run_daily_ingest(
                    session,
                    config,
                    source=args.source,
                    company=args.company,
                    limit=args.limit,
                    process=not args.metadata_only,
                    lock_ttl_minutes=args.lock_ttl_minutes,
                )
            else:
                run = curate_relevance(
                    session,
                    config,
                    company=args.company,
                    limit=args.limit or 500,
                )
            print(f"Job {run.id} {run.job_name}: {run.status}")
            pprint(run.metrics, sort_dicts=False)
            if run.error_message:
                print(run.error_message)
            if run.status == "failed":
                raise SystemExit(1)
            return

        if args.command == "summarize":
            summaries = pipeline.summarize_existing(args.company, args.days)
            for summary in summaries:
                print(f"[talk {summary.talk_id}] {summary.one_liner}")
            return

        if args.command == "compare":
            pprint(compare_company_topic(session, args.company, args.topic, args.limit), sort_dicts=False)
            return

        if args.command == "search":
            query = " ".join(args.query)
            vector_results = []
            try:
                vector_results = VectorStore(config.vector_store).search(query, limit=args.limit)
            except Exception as exc:
                print(f"Vector search unavailable: {exc}")
            text_results = postgres_text_search(session, query, limit=args.limit)
            pprint({"query": query, "vector_results": vector_results, "text_results": text_results}, sort_dicts=False)
            return


if __name__ == "__main__":
    main()
