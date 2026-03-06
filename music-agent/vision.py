from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import pytesseract

logger = logging.getLogger(__name__)


@dataclass
class SongGuess:
    artist: str
    title: str
    confidence_note: str


def _clean_fragment(value: str) -> str:
    value = value.strip().replace("’", "'")
    value = re.sub(r"^[^A-Za-z0-9']+", "", value)
    value = re.sub(r"[^A-Za-z0-9')]+$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    parts = value.split()
    if len(parts) >= 2 and len(parts[0]) <= 2 and parts[0].islower() and parts[1][:1].isupper():
        value = " ".join(parts[1:])
    return value


def _preprocess_image(image_path: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return thresh


def extract_text_from_image(image_path: Path, tesseract_psm: int = 6) -> str:
    processed = _preprocess_image(image_path)
    config = f"--oem 3 --psm {tesseract_psm}"
    text = pytesseract.image_to_string(processed, config=config)
    normalized = re.sub(r"\s+", " ", text).strip()
    logger.info("Extracted text: %s", normalized)
    return normalized


def detect_song_and_artist(extracted_text: str) -> SongGuess:
    """
    Best-effort parser for strings like:
    - 'One Dance - Drake'
    - 'Drake • One Dance'
    - 'One Dance by Drake'
    """
    text = extracted_text.strip()
    if not text:
        raise ValueError("No OCR text extracted from image.")

    normalized = re.sub(r"\s+", " ", text)
    normalized = normalized.replace("â€¢", "•").replace("â€”", "—").replace("â€“", "–")

    # Prefer right-most compact spans to avoid matching noisy UI text.
    dash_pattern = re.compile(r"([A-Za-z0-9'&., ]{2,40})\s*[-–—•]\s*([A-Za-z0-9'&., ]{2,60})")
    by_pattern = re.compile(r"([A-Za-z0-9'&., ]{2,60})\s+by\s+([A-Za-z0-9'&., ]{2,40})", re.IGNORECASE)

    dash_matches = list(dash_pattern.finditer(normalized))
    if dash_matches:
        last = dash_matches[-1]
        left = _clean_fragment(last.group(1))
        right = _clean_fragment(last.group(2))
        if left and right:
            return SongGuess(artist=left, title=right, confidence_note="parsed using right-most dash pattern")

    by_matches = list(by_pattern.finditer(normalized))
    if by_matches:
        last = by_matches[-1]
        left = _clean_fragment(last.group(1))
        right = _clean_fragment(last.group(2))
        if left and right:
            return SongGuess(artist=right, title=left, confidence_note="parsed using right-most 'by' pattern")

    chunks = re.split(r"[|,]", normalized)
    title = _clean_fragment(chunks[0]) if chunks else "Unknown Song"
    if not title:
        title = "Unknown Song"
    return SongGuess(artist="Unknown Artist", title=title, confidence_note="fallback parsing")
