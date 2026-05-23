from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MediaCandidate(BaseModel):
    source: str
    title: str
    url: str
    published_at: datetime | None = None
    duration_seconds: int | None = None
    description: str | None = None
    external_id: str | None = None
    audio_url: str | None = None
    feed_name: str | None = None
    thumbnail_url: str | None = None


class RelevanceResult(BaseModel):
    passed: bool
    score: float
    company_ticker: str
    executive_name: str | None = None
    executive_role: str | None = None
    reasons: list[str] = Field(default_factory=list)


class TranscriptSegmentPayload(BaseModel):
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str | None = None


class TranscriptPayload(BaseModel):
    language: str | None = None
    segments: list[TranscriptSegmentPayload]

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments if segment.text.strip())


class SummaryPayload(BaseModel):
    one_liner: str
    management_tone: str
    core_topics: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    quotes: list[str] = Field(default_factory=list)
    changes_vs_prior: str | None = None
    investable_hypotheses: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    source_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

