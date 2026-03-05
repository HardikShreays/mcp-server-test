from __future__ import annotations

import logging
import re
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar


T = TypeVar("T")


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def sanitize_filename(value: str) -> str:
    value = value.strip().replace("/", "-")
    value = re.sub(r"[<>:\\|?*\x00-\x1F]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value[:200]


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def retry(max_retries: int, backoff_seconds: float) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt == max_retries:
                        break
                    sleep_s = backoff_seconds * attempt
                    logging.getLogger(func.__module__).warning(
                        "Attempt %s/%s failed for %s: %s. Retrying in %.1fs...",
                        attempt,
                        max_retries,
                        func.__name__,
                        exc,
                        sleep_s,
                    )
                    time.sleep(sleep_s)
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator
