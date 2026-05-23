from __future__ import annotations

from datetime import datetime, timezone

from yt_dlp import YoutubeDL

from ceo_talk_monitor.config import CompanyConfig, YoutubeSourceConfig
from ceo_talk_monitor.schemas import MediaCandidate


def _parse_upload_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class YoutubeCollector:
    def __init__(self, config: YoutubeSourceConfig):
        self.config = config

    def build_queries(self, company: CompanyConfig) -> list[str]:
        queries: list[str] = []
        for executive in company.executives:
            for template in self.config.query_templates:
                queries.append(
                    template.format(
                        ticker=company.ticker,
                        company=company.aliases[0] if company.aliases else company.name,
                        executive=executive.name,
                        role=executive.role,
                    )
                )
        queries.extend(company.search_terms)
        return list(dict.fromkeys(queries))

    def search_company(self, company: CompanyConfig) -> list[MediaCandidate]:
        candidates: dict[str, MediaCandidate] = {}
        for candidate in self.fetch_channel_recent(self.config.channel_recent_limit):
            candidates[candidate.url] = candidate
        search_added = 0
        for query in self.build_queries(company):
            for candidate in self.search(query, self.config.search_limit_per_query):
                if candidate.url not in candidates:
                    search_added += 1
                candidates[candidate.url] = candidate
                if search_added >= self.config.max_items_per_company:
                    return list(candidates.values())
        return list(candidates.values())

    def fetch_channel_recent(self, limit: int = 20) -> list[MediaCandidate]:
        if not self.config.cnbc_channel_url or limit <= 0:
            return []
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "playlistend": limit,
        }
        url = self.config.cnbc_channel_url.rstrip("/") + "/videos"
        try:
            with YoutubeDL(opts) as ydl:
                payload = ydl.extract_info(url, download=False)
        except Exception:
            return []
        return [candidate for candidate in self._entries_to_candidates(payload.get("entries", []) if payload else [])]

    def search(self, query: str, limit: int = 5) -> list[MediaCandidate]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        search_query = f"ytsearch{limit}:{query}"
        with YoutubeDL(opts) as ydl:
            payload = ydl.extract_info(search_query, download=False)

        entries = payload.get("entries", []) if payload else []
        return self._entries_to_candidates(entries)

    def _entries_to_candidates(self, entries) -> list[MediaCandidate]:
        candidates: list[MediaCandidate] = []
        for entry in entries:
            if not entry:
                continue
            video_id = entry.get("id")
            url = entry.get("url") or entry.get("webpage_url")
            if video_id and (not url or not str(url).startswith("http")):
                url = f"https://www.youtube.com/watch?v={video_id}"
            if not url:
                continue
            title = entry.get("title") or ""
            description = " ".join(
                filter(
                    None,
                    [
                        entry.get("description"),
                        entry.get("channel"),
                        entry.get("uploader"),
                    ],
                )
            )
            candidates.append(
                MediaCandidate(
                    source="youtube",
                    title=title,
                    url=url,
                    external_id=video_id,
                    published_at=_parse_upload_date(entry.get("upload_date")),
                    duration_seconds=entry.get("duration"),
                    description=description,
                    thumbnail_url=entry.get("thumbnail"),
                )
            )
        return candidates
