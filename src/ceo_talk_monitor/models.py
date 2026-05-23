from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON}


JsonType = JSON().with_variant(JSONB, "postgresql")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    executives: Mapped[list["Executive"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    talks: Mapped[list["Talk"]] = relationship(back_populates="company")


class Executive(Base):
    __tablename__ = "executives"
    __table_args__ = (UniqueConstraint("company_id", "name", "role", name="uq_executive_company_name_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(64))
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list)

    company: Mapped[Company] = relationship(back_populates="executives")


class Talk(Base):
    __tablename__ = "talks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    company_ticker: Mapped[str] = mapped_column(String(16), index=True)
    executive_name: Mapped[str | None] = mapped_column(String(255), index=True)
    executive_role: Mapped[str | None] = mapped_column(String(64))
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    relevance_reasons: Mapped[list[str]] = mapped_column(JsonType, default=list)
    audio_path: Mapped[str | None] = mapped_column(Text)
    transcript_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company | None] = relationship(back_populates="talks")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="talk", cascade="all, delete-orphan", order_by="TranscriptSegment.start_seconds"
    )
    summary: Mapped["Summary | None"] = relationship(back_populates="talk", cascade="all, delete-orphan")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    talk_id: Mapped[int] = mapped_column(ForeignKey("talks.id", ondelete="CASCADE"), index=True)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    speaker: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)

    talk: Mapped[Talk] = relationship(back_populates="transcript_segments")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    talk_id: Mapped[int] = mapped_column(ForeignKey("talks.id", ondelete="CASCADE"), unique=True, index=True)
    one_liner: Mapped[str] = mapped_column(Text)
    management_tone: Mapped[str] = mapped_column(String(64))
    core_topics: Mapped[list[str]] = mapped_column(JsonType, default=list)
    signals: Mapped[dict] = mapped_column(JsonType, default=dict)
    quotes: Mapped[list[str]] = mapped_column(JsonType, default=list)
    changes_vs_prior: Mapped[str | None] = mapped_column(Text)
    investable_hypotheses: Mapped[list[str]] = mapped_column(JsonType, default=list)
    risks: Mapped[list[str]] = mapped_column(JsonType, default=list)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_summary: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    talk: Mapped[Talk] = relationship(back_populates="summary")

