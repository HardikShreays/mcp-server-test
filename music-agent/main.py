from __future__ import annotations

import argparse
import logging
from pathlib import Path

from config import Settings
from downloader import download_preview_as_mp3, is_already_downloaded, target_mp3_path
from search import search_song_preview
from utils import retry, setup_logging
from vision import detect_song_and_artist, extract_text_from_image

logger = logging.getLogger(__name__)


def run(image_path: Path) -> Path:
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    if not image_path.exists():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    extract = retry(settings.max_retries, settings.retry_backoff_seconds)(extract_text_from_image)
    search = retry(settings.max_retries, settings.retry_backoff_seconds)(search_song_preview)
    download = retry(settings.max_retries, settings.retry_backoff_seconds)(download_preview_as_mp3)

    extracted_text = extract(image_path, settings.tesseract_psm)
    guess = detect_song_and_artist(extracted_text)

    logger.info("Detected Song:\nArtist: %s\nSong: %s", guess.artist, guess.title)

    result = search(guess.title, guess.artist, settings.user_agent)
    out_path = target_mp3_path(settings.base_download_dir, result.artist, result.title)

    if is_already_downloaded(out_path):
        logger.info("Download status: skipped (already downloaded) -> %s", out_path)
        return out_path

    logger.info("Downloading...")
    saved = download(result.preview_url, out_path)
    logger.info("Saved to:\n%s", saved)
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract song metadata from a screenshot and download a legal preview audio file "
            "to downloads/music/<artist>/<song>.mp3"
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
