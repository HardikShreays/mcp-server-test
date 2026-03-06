from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    artist: str
    title: str
    preview_url: str
    source_url: str


def _itunes_search(query: str, user_agent: str, timeout_s: int) -> list[dict]:
    params = {"term": query, "entity": "song", "limit": 5}
    headers = {"User-Agent": user_agent}
    response = requests.get("https://itunes.apple.com/search", params=params, headers=headers, timeout=timeout_s)
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        candidate = " ".join(value.split()).strip()
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def search_song_preview(song_title: str, artist: str, user_agent: str, timeout_s: int = 15) -> SearchResult:
    """
    Search iTunes API for a legal preview URL.
    Includes fallback query strategies for noisy OCR and artist/title inversion.
    """
    queries = _unique_non_empty(
        [
            f"{song_title} {artist}",
            f"{artist} {song_title}",
            song_title,
            artist,
        ]
    )

    for query in queries:
        results = _itunes_search(query, user_agent, timeout_s)
        if not results:
            continue

        best = next((r for r in results if r.get("previewUrl")), None)
        if not best:
            continue

        found = SearchResult(
            artist=best.get("artistName", artist),
            title=best.get("trackName", song_title),
            preview_url=best["previewUrl"],
            source_url=best.get("trackViewUrl", ""),
        )
        logger.info("Detected song: artist='%s', title='%s'", found.artist, found.title)
        logger.info("Search source URL: %s", found.source_url)
        logger.info("Search query used: %s", query)
        return found

    full_query = f"{song_title} {artist}".strip()
    raise LookupError(f"No results found for: {full_query}")
