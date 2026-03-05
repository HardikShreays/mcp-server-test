from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the music agent."""

    base_download_dir: Path = Path("downloads/music")
    log_level: str = "INFO"
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    user_agent: str = "music-agent/1.0"

    # OCR tunables
    tesseract_psm: int = 6

    @staticmethod
    def from_env() -> "Settings":
        base_dir = Path(os.getenv("MUSIC_AGENT_DOWNLOAD_DIR", "downloads/music"))
        log_level = os.getenv("MUSIC_AGENT_LOG_LEVEL", "INFO")
        max_retries = int(os.getenv("MUSIC_AGENT_MAX_RETRIES", "3"))
        retry_backoff = float(os.getenv("MUSIC_AGENT_RETRY_BACKOFF", "1.5"))
        tesseract_psm = int(os.getenv("MUSIC_AGENT_TESSERACT_PSM", "6"))

        return Settings(
            base_download_dir=base_dir,
            log_level=log_level,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff,
            tesseract_psm=tesseract_psm,
        )
