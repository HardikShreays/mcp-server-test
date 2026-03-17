from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

from utils import ensure_directory, sanitize_filename

logger = logging.getLogger(__name__)


def target_mp3_path(base_dir: Path, artist: str, title: str) -> Path:
    safe_artist = sanitize_filename(artist or "Unknown Artist")
    safe_title = sanitize_filename(title or "Unknown Song")
    return base_dir / safe_artist / f"{safe_title}.mp3"


def is_already_downloaded(target_path: Path) -> bool:
    return target_path.exists() and target_path.stat().st_size > 0


@dataclass(frozen=True)
class YouTubeSearchResult:
    video_id: str
    url: str
    title: str
    uploader: str
    duration: int | None


def _normalize_search_entry(entry: dict[str, Any]) -> YouTubeSearchResult:
    video_id = entry.get("id") or entry.get("video_id") or ""
    url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
    return YouTubeSearchResult(
        video_id=video_id,
        url=url,
        title=entry.get("title", ""),
        uploader=entry.get("uploader", "") or entry.get("channel", "") or "",
        duration=entry.get("duration"),
    )


def search_youtube_songs(query: str, limit: int = 5) -> list[YouTubeSearchResult]:
    """
    Search YouTube for songs using yt-dlp's ytsearch.

    Returns up to `limit` normalized search results suitable for presenting
    to a user (e.g., top 5 candidates).
    """
    if not query.strip():
        raise ValueError("Search query must not be empty.")

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "default_search": "ytsearch",
    }

    search_term = f"ytsearch{limit}:{query}"
    logger.info("Searching YouTube for query: %s", search_term)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_term, download=False)

    entries = info.get("entries") or []
    results = [_normalize_search_entry(entry) for entry in entries[:limit]]

    logger.info("YouTube search returned %d results", len(results))
    return results


def parse_artist_title_from_metadata(info: dict[str, Any]) -> tuple[str, str]:
    """
    Derive (artist, title) from yt-dlp metadata.

    Heuristics:
    - If the title contains a single '-', treat as 'artist - title'.
    - Otherwise, use uploader as artist (if available) and full title as song title.
    """
    raw_title = (info.get("title") or "").strip()
    uploader = (info.get("uploader") or info.get("channel") or "").strip()

    artist = uploader or "Unknown Artist"
    title = raw_title or "Unknown Song"

    if "-" in raw_title:
        parts = [p.strip() for p in raw_title.split("-", maxsplit=1)]
        if len(parts) == 2 and all(parts):
            artist, title = parts[0], parts[1]

    return artist, title


def yt_downloader(video_url: str, base_dir: Path) -> Path:
    """
    Download a YouTube video as MP3 into base_dir/Artist/Title.mp3.
    """
    if not video_url.strip():
        raise ValueError("Video URL must not be empty.")

    # First fetch metadata to determine artist/title and final output path.
    probe_opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    artist, title = parse_artist_title_from_metadata(info)
    target_path = target_mp3_path(base_dir, artist, title)

    if is_already_downloaded(target_path):
        logger.info("File already downloaded at %s; skipping download.", target_path)
        return target_path

    ensure_directory(target_path.parent)

    ydl_opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(target_path.with_suffix(".%(ext)s")),
        "noplaylist": True,
        "quiet": False,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    logger.info("Starting download for URL %s -> %s", video_url, target_path)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # After postprocessing, yt-dlp should have produced an mp3 at target_path.
    if not target_path.exists():
        # Fallback: try with explicit .mp3 suffix in case template handling differs.
        fallback = target_path.with_suffix(".mp3")
        if fallback.exists():
            return fallback
        raise FileNotFoundError(f"Expected downloaded file not found at {target_path}")

    logger.info("Download complete: %s", target_path)
    return target_path
