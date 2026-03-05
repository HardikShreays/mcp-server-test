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

    separators = [" - ", " • ", " by ", " — ", " – "]
    for sep in separators:
        if sep in text:
            left, right = [part.strip() for part in text.split(sep, 1)]
            if sep == " by ":
                return SongGuess(artist=right, title=left, confidence_note=f"parsed using '{sep.strip()}'")
            # heuristic: if left has many words and right is short, assume right is artist
            if len(right.split()) <= 4:
                return SongGuess(artist=right, title=left, confidence_note=f"parsed using '{sep.strip()}'")
            return SongGuess(artist=left, title=right, confidence_note=f"parsed using '{sep.strip()}'")

    # fallback: first two chunks from OCR as title/artist unknown
    chunks = re.split(r"[|,]", text)
    title = chunks[0].strip()
    return SongGuess(artist="Unknown Artist", title=title, confidence_note="fallback parsing")
