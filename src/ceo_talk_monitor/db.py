from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ceo_talk_monitor.config import AppConfig, get_settings
from ceo_talk_monitor.models import Base, Company, Executive


def make_engine(database_url: str | None = None):
    settings = get_settings()
    return create_engine(database_url or settings.database_url, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def upsert_config_companies(session: Session, config: AppConfig) -> None:
    for company_cfg in config.companies:
        company = session.scalar(select(Company).where(Company.ticker == company_cfg.ticker.upper()))
        if company is None:
            company = Company(ticker=company_cfg.ticker.upper(), name=company_cfg.name, aliases=company_cfg.aliases)
            session.add(company)
            session.flush()
        else:
            company.name = company_cfg.name
            company.aliases = company_cfg.aliases

        existing = {
            (executive.name.lower(), executive.role.lower()): executive
            for executive in company.executives
        }
        for executive_cfg in company_cfg.executives:
            key = (executive_cfg.name.lower(), executive_cfg.role.lower())
            executive = existing.get(key)
            if executive is None:
                session.add(
                    Executive(
                        company_id=company.id,
                        name=executive_cfg.name,
                        role=executive_cfg.role,
                        aliases=executive_cfg.aliases,
                    )
                )
            else:
                executive.aliases = executive_cfg.aliases
    session.commit()

