from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

from utils import ensure_directory, sanitize_filename

logger = logging.getLogger(__name__)


def resolve_ffmpeg_location() -> str | None:
    """
    Resolve ffmpeg binary location for yt-dlp.

    Priority:
    1) MUSIC_AGENT_FFMPEG_LOCATION env var (explicit override)
    2) ffmpeg available on PATH
    3) Common winget install location on Windows
    """
    explicit = os.getenv("MUSIC_AGENT_FFMPEG_LOCATION", "").strip()
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.exists():
            return str(explicit_path)

    ffmpeg_on_path = shutil.which("ffmpeg")
    if ffmpeg_on_path:
        return ffmpeg_on_path

    winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    winget_candidates = sorted(winget_root.glob("Gyan.FFmpeg_*"))
    for candidate in winget_candidates:
        bin_dir = candidate / "ffmpeg-8.1-full_build" / "bin"
        ffmpeg_exe = bin_dir / "ffmpeg.exe"
        if ffmpeg_exe.exists():
            return str(bin_dir)

        any_ffmpeg = list(candidate.glob("**/bin/ffmpeg.exe"))
        if any_ffmpeg:
            return str(any_ffmpeg[0].parent)

    return None


def resolve_js_runtimes() -> dict[str, dict[str, str | None]]:
    """
    Resolve JavaScript runtime config for yt-dlp EJS extraction.

    Returns a dict in yt-dlp's expected format:
    {"runtime_name": {"path": <optional path>}}
    """
    explicit = os.getenv("MUSIC_AGENT_JS_RUNTIME_PATH", "").strip()
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.exists():
            return {"deno": {"path": str(explicit_path)}}

    deno_on_path = shutil.which("deno")
    if deno_on_path:
        return {"deno": {"path": deno_on_path}}

    winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    deno_candidates = sorted(winget_root.glob("DenoLand.Deno_*"))
    for candidate in deno_candidates:
        deno_exe = candidate / "deno.exe"
        if deno_exe.exists():
            return {"deno": {"path": str(deno_exe)}}

        nested = list(candidate.glob("**/deno.exe"))
        if nested:
            return {"deno": {"path": str(nested[0])}}

    # Fallback to yt-dlp default; may warn if no runtime is available.
    return {"deno": {}}


def build_runtime_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "js_runtimes": resolve_js_runtimes(),
    }

    ffmpeg_location = resolve_ffmpeg_location()
    if ffmpeg_location:
        opts["ffmpeg_location"] = ffmpeg_location

    return opts


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
        **build_runtime_opts(),
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
        **build_runtime_opts(),
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
        **build_runtime_opts(),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if "ffmpeg_location" not in ydl_opts:
        logger.warning("ffmpeg not found. Audio conversion quality may be limited.")

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
