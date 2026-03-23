from __future__ import annotations

import argparse
import logging
from pathlib import Path

from config import Settings
from downloader import search_youtube_songs, yt_downloader
from utils import retry, setup_logging
from vision import detect_song_and_artist, extract_text_from_image

logger = logging.getLogger(__name__)


def _build_query(title: str, artist: str) -> str:
    parts = [s.strip() for s in (title, artist) if s and s.strip()]
    return " ".join(parts) if parts else ""


def run(image_path: Path) -> Path:
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    if not image_path.exists():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    extract = retry(settings.max_retries, settings.retry_backoff_seconds)(extract_text_from_image)
    search = retry(settings.max_retries, settings.retry_backoff_seconds)(search_youtube_songs)
    download = retry(settings.max_retries, settings.retry_backoff_seconds)(yt_downloader)

    extracted_text = extract(image_path, settings.tesseract_psm)
    guess = detect_song_and_artist(extracted_text)

    logger.info("Detected Song:\nArtist: %s\nSong: %s", guess.artist, guess.title)

    query = _build_query(guess.title, guess.artist)
    if not query:
        raise ValueError("Could not detect song or artist from the image.")

    results = search(query, limit=5)
    if not results:
        raise LookupError(f"No YouTube results for: {query}")

    # Use first result for non-interactive CLI
    first = results[0]
    logger.info("Downloading: %s - %s", first.uploader, first.title)

    saved = download(first.url, settings.base_download_dir)
    logger.info("Saved to: %s", saved)
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract song metadata from a screenshot, search YouTube, and download "
            "the top result to downloads/music/<artist>/<song>.mp3"
        )
    )
    parser.add_argument("image_path", type=Path, help="Path to screenshot image")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args.image_path)


if __name__ == "__main__":
    main()
