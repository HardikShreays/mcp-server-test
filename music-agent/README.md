# Music Agent (OCR + Song Lookup)

A modular Python CLI app that:
1. Reads a screenshot from disk.
2. Uses OCR to extract song text.
3. Detects likely artist/title.
4. Searches online using API metadata.
5. Downloads an audio preview and stores it as:

`downloads/music/<artist>/<song>.mp3`

> **Important legal note**
> This project is implemented for lawful use-cases (e.g., downloading provider-exposed preview clips or content you are authorized to save). Respect copyright and platform terms.

## Project Structure

```text
music-agent/
  main.py
  vision.py
  search.py
  downloader.py
  utils.py
  config.py
  requirements.txt
  README.md
```

## Setup

### 1) System dependencies

Install Tesseract OCR:

- Ubuntu/Debian:
  ```bash
  sudo apt-get update && sudo apt-get install -y tesseract-ocr
  ```
- macOS:
  ```bash
  brew install tesseract
  ```

### Windows setup (PowerShell)

Install prerequisites:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id UB-Mannheim.TesseractOCR
```

Then open a **new** PowerShell window and set up the project:

```powershell
cd C:\Users\ritshrey\IdeaProjects\mcp-server-test\music-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `tesseract` is still not found after install, add its install directory to `PATH`
(commonly `C:\Program Files\Tesseract-OCR`) and restart PowerShell.

### 2) Python env

```bash
cd music-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python main.py screenshot.png
```

Example logs:

```text
Detected Song:
Artist: Drake
Song: One Dance
Downloading...
Saved to:
downloads/music/Drake/One Dance.mp3
```

## Notes

- Automatic retry is built in for OCR/search/download network steps.
- Deduplication: if target file already exists and is non-empty, download is skipped.
- OCR quality strongly depends on screenshot quality.
- Although `yt-dlp` is included in dependencies per requested stack, this reference implementation uses a provider preview API for legal-friendly retrieval.

## Environment Variables

- `MUSIC_AGENT_DOWNLOAD_DIR` (default: `downloads/music`)
- `MUSIC_AGENT_LOG_LEVEL` (default: `INFO`)
- `MUSIC_AGENT_MAX_RETRIES` (default: `3`)
- `MUSIC_AGENT_RETRY_BACKOFF` (default: `1.5`)
- `MUSIC_AGENT_TESSERACT_PSM` (default: `6`)
