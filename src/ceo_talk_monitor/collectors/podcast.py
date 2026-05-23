from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ceo_talk_monitor.config import PodcastFeedConfig
from ceo_talk_monitor.schemas import MediaCandidate


def _parse_duration(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    parts = str(value).split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = [int(float(part)) for part in parts]
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes, seconds = [int(float(part)) for part in parts]
            return minutes * 60 + seconds
        return int(float(str(value)))
    except ValueError:
        return None


def _parse_published(entry) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if value:
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc)
        except (TypeError, ValueError, AttributeError):
            return None
    return None


class PodcastCollector:
    def fetch_feed(self, feed: PodcastFeedConfig, limit: int = 30) -> list[MediaCandidate]:
        parsed = feedparser.parse(feed.url)
        candidates: list[MediaCandidate] = []
        for entry in parsed.entries[:limit]:
            audio_url = None
            for enclosure in entry.get("enclosures", []):
                href = enclosure.get("href")
                media_type = enclosure.get("type", "")
                if href and ("audio" in media_type or href.endswith((".mp3", ".m4a", ".wav"))):
                    audio_url = href
                    break
            if not audio_url:
                continue
            candidates.append(
                MediaCandidate(
                    source="podcast",
                    title=entry.get("title", ""),
                    url=entry.get("link") or audio_url,
                    external_id=entry.get("id") or entry.get("guid"),
                    published_at=_parse_published(entry),
                    duration_seconds=_parse_duration(entry.get("itunes_duration")),
                    description=entry.get("summary") or entry.get("description"),
                    audio_url=audio_url,
                    feed_name=feed.name,
                )
            )
        return candidates

