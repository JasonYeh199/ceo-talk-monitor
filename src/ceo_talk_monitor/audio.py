from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx
from yt_dlp import YoutubeDL


def safe_slug(value: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug[:max_length] or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def download_youtube_audio(url: str, output_dir: str | Path, stem: str) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    final_path = output_path / f"{safe_slug(stem)}.mp3"
    if final_path.exists():
        return final_path

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_path / f"{safe_slug(stem)}.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    return final_path


def download_url_audio(url: str, output_dir: str | Path, stem: str) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    extension = Path(url.split("?")[0]).suffix or ".mp3"
    final_path = output_path / f"{safe_slug(stem)}{extension}"
    if final_path.exists():
        return final_path

    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with final_path.open("wb") as handle:
            for chunk in response.iter_bytes():
                if chunk:
                    handle.write(chunk)
    return final_path

