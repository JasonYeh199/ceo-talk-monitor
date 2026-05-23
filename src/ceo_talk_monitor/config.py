from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ceo_talk:ceo_talk@localhost:5432/ceo_talk"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str | None = None
    openai_summary_model: str | None = None
    app_config_path: str = "config.yaml"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class SourceMetadata(BaseModel):
    name: str
    url: str | None = None
    retrieved_at: str | None = None
    notes: str | None = None


class PortfolioConfig(BaseModel):
    name: str
    as_of: str
    source: SourceMetadata
    tickers: list[str]


class ExecutiveConfig(BaseModel):
    name: str
    role: str
    aliases: list[str] = Field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        return [self.name, *self.aliases]


class CompanyConfig(BaseModel):
    ticker: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    executives: list[ExecutiveConfig] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)

    @property
    def all_company_names(self) -> list[str]:
        return [self.ticker, self.name, *self.aliases]


class YoutubeSourceConfig(BaseModel):
    enabled: bool = True
    search_limit_per_query: int = 5
    channel_recent_limit: int = 20
    max_items_per_company: int = 10
    cnbc_channel_url: str | None = None
    query_templates: list[str] = Field(default_factory=list)


class PodcastFeedConfig(BaseModel):
    name: str
    url: str


class PodcastSourceConfig(BaseModel):
    enabled: bool = True
    max_entries_per_feed: int = 30
    feeds: list[PodcastFeedConfig] = Field(default_factory=list)


class SourcesConfig(BaseModel):
    youtube: YoutubeSourceConfig = Field(default_factory=YoutubeSourceConfig)
    podcasts: PodcastSourceConfig = Field(default_factory=PodcastSourceConfig)


class RelevanceConfig(BaseModel):
    threshold: float = 7.0
    include_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)


class DiarizationConfig(BaseModel):
    enabled: bool = False


class TranscriptionConfig(BaseModel):
    provider: str = "faster_whisper"
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = "en"
    diarization: DiarizationConfig = Field(default_factory=DiarizationConfig)


class SummarizationConfig(BaseModel):
    provider: str = "heuristic"
    model: str = "gpt-4.1-mini"
    max_transcript_chars: int = 20000
    output_language: str = "zh-TW"


class VectorStoreConfig(BaseModel):
    provider: str = "qdrant"
    collection_name: str = "ceo_talk_transcripts"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


class StorageConfig(BaseModel):
    audio_dir: str = "data/audio"
    transcript_dir: str = "data/transcripts"


class AppConfig(BaseModel):
    portfolio: PortfolioConfig
    companies: list[CompanyConfig]
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    relevance: RelevanceConfig = Field(default_factory=RelevanceConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    summarization: SummarizationConfig = Field(default_factory=SummarizationConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    def company_by_ticker(self, ticker: str) -> CompanyConfig:
        normalized = ticker.upper()
        for company in self.companies:
            if company.ticker.upper() == normalized:
                return company
        raise KeyError(f"Unknown company ticker: {ticker}")

    def tracked_companies(self) -> list[CompanyConfig]:
        tracked = {ticker.upper() for ticker in self.portfolio.tickers}
        return [company for company in self.companies if company.ticker.upper() in tracked]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)
    return AppConfig.model_validate(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=2)
def get_config(path: str | None = None) -> AppConfig:
    settings = get_settings()
    return load_config(path or settings.app_config_path)


def ensure_storage_dirs(config: AppConfig) -> None:
    Path(config.storage.audio_dir).mkdir(parents=True, exist_ok=True)
    Path(config.storage.transcript_dir).mkdir(parents=True, exist_ok=True)
