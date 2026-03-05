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


def search_song_preview(song_title: str, artist: str, user_agent: str, timeout_s: int = 15) -> SearchResult:
    """
    Search iTunes API for a legal preview URL.
    """
    query = f"{song_title} {artist}".strip()
    params = {"term": query, "entity": "song", "limit": 5}
    headers = {"User-Agent": user_agent}

    response = requests.get("https://itunes.apple.com/search", params=params, headers=headers, timeout=timeout_s)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])

    if not results:
        raise LookupError(f"No results found for: {query}")

    best = next((r for r in results if r.get("previewUrl")), None)
    if not best:
        raise LookupError(f"No downloadable preview found for: {query}")

    found = SearchResult(
        artist=best.get("artistName", artist),
        title=best.get("trackName", song_title),
        preview_url=best["previewUrl"],
        source_url=best.get("trackViewUrl", ""),
    )
    logger.info("Detected song: artist='%s', title='%s'", found.artist, found.title)
    logger.info("Search source URL: %s", found.source_url)
    return found
