from __future__ import annotations

import logging
from pathlib import Path

import requests

from utils import ensure_directory, sanitize_filename

logger = logging.getLogger(__name__)


def target_mp3_path(base_dir: Path, artist: str, title: str) -> Path:
    safe_artist = sanitize_filename(artist or "Unknown Artist")
    safe_title = sanitize_filename(title or "Unknown Song")
    return base_dir / safe_artist / f"{safe_title}.mp3"


def is_already_downloaded(target_path: Path) -> bool:
    return target_path.exists() and target_path.stat().st_size > 0


def download_preview_as_mp3(preview_url: str, destination: Path, timeout_s: int = 30) -> Path:
    """
    Downloads the remote preview bytes and stores them with .mp3 extension.

    Note: preview assets from provider APIs may be AAC/M4A encoded. We preserve bytes
    as delivered and place in target path for a simple end-to-end workflow.
    """
    ensure_directory(destination.parent)
    with requests.get(preview_url, stream=True, timeout=timeout_s) as response:
        response.raise_for_status()
        with destination.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    logger.info("Download status: success (%s)", destination)
    return destination
