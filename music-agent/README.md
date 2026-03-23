# Music Agent (OCR + YouTube Request + Admin Download)

A Python web app that supports two roles:
1. **User UI** (`/user`): search by text or upload screenshot (OCR), view top YouTube matches, and submit a **Request** for an exact selected song/video.
2. **Admin UI** (`/admin`): view requested songs and perform **Download** (admin-only).

Downloaded files are stored under:

`downloads/music/<artist>/<song>.mp3`

> **Important legal note**
> This project is implemented for lawful use-cases (e.g., downloading provider-exposed preview clips or content you are authorized to save). Respect copyright and platform terms.

## Project Structure

```text
music-agent/
  app.py
  main.py
  vision.py
  search.py
  downloader.py
  utils.py
  config.py
  templates/
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
python app.py
```

Then open:

- User page: `http://127.0.0.1:5000/user`
- Admin page: `http://127.0.0.1:5000/admin?role=admin`

## Web Flow

### User Flow (`/user`)

1. **Request By Text** (`Song Title`, `Artist Name`) or **Request By Screenshot** (png/jpg/jpeg/bmp/webp).
2. App searches YouTube and shows top matches.
3. User clicks **Request** on the exact result.
4. Request is added to Admin Dashboard.

### Admin Flow (`/admin`)

1. View submitted requests (Request ID, type, title/artist, extracted text, status, created time when available).
2. Click **Download** for requested items.
3. File is downloaded to `downloads/music/...`.

## Optional CLI Usage

The original CLI entrypoint is still available:

```bash
python main.py screenshot.png
```

Example CLI logs:

```text
Detected Song:
Artist: Drake
Song: One Dance
Downloading...
Saved to:
downloads/music/Drake/One Dance.mp3
```

## Notes

- Automatic retry is built in for OCR/search/download steps.
- Downloads are admin-only in the web UI.
- Deduplication: if target file already exists and is non-empty, download may be skipped.
- OCR quality strongly depends on screenshot quality.
- Role routing:
  - Non-admin access to `/admin` redirects to `/user`.
  - Role can be provided via `?role=admin|user`, `X-Role` header, or `MUSIC_AGENT_DEFAULT_ROLE`.

## Environment Variables

- `MUSIC_AGENT_DOWNLOAD_DIR` (default: `downloads/music`)
- `MUSIC_AGENT_LOG_LEVEL` (default: `INFO`)
- `MUSIC_AGENT_MAX_RETRIES` (default: `3`)
- `MUSIC_AGENT_RETRY_BACKOFF` (default: `1.5`)
- `MUSIC_AGENT_TESSERACT_PSM` (default: `6`)
- `MUSIC_AGENT_DEFAULT_ROLE` (default: `user`)
