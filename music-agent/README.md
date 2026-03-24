# Music Agent (OCR + YouTube Request + Admin Download)

A Python web app that supports two roles:
1. **User UI** (`/user`): search by text or upload screenshot (OCR), choose an **Admin** from dropdown, view top YouTube matches, and submit a **Request** for an exact selected song/video.
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
  database.py
  models.py
  repository.py
  alembic/
  scripts/
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

### 3) Database (PostgreSQL)

Set `DATABASE_URL`:

```powershell
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/music_agent"
```

or on Linux/macOS:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/music_agent"
```

Run migrations:

```bash
alembic upgrade head
```

Seed initial users/admins:

```bash
python scripts/seed_db.py
```

## Usage

```bash
python app.py
```

Then open:

- User page: `http://127.0.0.1:5000/user`
- Admin page: `http://127.0.0.1:5000/admin`
- Login page: `http://127.0.0.1:5000/login`

From login page you can:
- Sign in as existing User/Admin.
- Create a new **User** or **Admin** account (stored in `users` table with hashed password).

## Web Flow

### User Flow (`/user`)

1. **Request By Text** (`Song Title`, `Artist Name`) or **Request By Screenshot** (png/jpg/jpeg/bmp/webp).
2. Select target **Admin** from dropdown.
3. App searches YouTube and shows top matches.
4. User clicks **Request** on the exact result.
5. Request is assigned to the selected admin.

### Admin Flow (`/admin`)

1. View submitted requests (Request ID, type, title/artist, extracted text, status, created time when available).
2. See only requests assigned to the logged-in admin.
3. Click **Download** for requested items.
4. Download history is recorded in `downloads` table.
5. File is downloaded to `downloads/music/...`.

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
- Admin page supports **Direct Folder Save** (Chromium browsers with File System Access API):
  - Set download folder once from Admin dashboard.
  - Future downloads save directly there.
  - If unsupported/permission denied, app falls back to normal browser download.
- Deduplication: if target file already exists and is non-empty, download may be skipped.
- OCR quality strongly depends on screenshot quality.
- Auth routing:
  - Not logged in: `/user` and `/admin` redirect to `/login`.
  - Requestor cannot access `/admin`.
  - Admin cannot access requestor-only `/user` workflow.

## Environment Variables

- `MUSIC_AGENT_DOWNLOAD_DIR` (default: `downloads/music`)
- `MUSIC_AGENT_LOG_LEVEL` (default: `INFO`)
- `MUSIC_AGENT_MAX_RETRIES` (default: `3`)
- `MUSIC_AGENT_RETRY_BACKOFF` (default: `1.5`)
- `MUSIC_AGENT_TESSERACT_PSM` (default: `6`)
- `MUSIC_AGENT_SECRET_KEY` (required in production)
- `DATABASE_URL` (e.g. `postgresql://postgres:postgres@localhost:5432/music_agent`)
