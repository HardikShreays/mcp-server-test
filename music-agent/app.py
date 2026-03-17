from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from config import Settings
from downloader import search_youtube_songs, yt_downloader
from utils import ensure_directory, retry, setup_logging
from vision import detect_song_and_artist, extract_text_from_image

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _is_allowed_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _build_search_query(song_title: str, artist: str) -> str:
    parts = [s.strip() for s in (song_title, artist) if s and s.strip()]
    return " ".join(parts) if parts else ""


def _safe_download_path(file_path: str, base_dir: Path) -> Path:
    requested = Path(file_path)
    resolved_base = base_dir.resolve()
    resolved_path = requested.resolve()

    try:
        resolved_path.relative_to(resolved_base)
    except ValueError as exc:
        raise PermissionError("Invalid download path.") from exc

    if not resolved_path.exists() or not resolved_path.is_file():
        raise FileNotFoundError(file_path)

    return resolved_path


def create_app() -> Flask:
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

    upload_dir = Path("uploads")
    ensure_directory(upload_dir)

    @app.route("/", methods=["GET", "POST"])
    def index():
        error: str | None = None
        result: dict | None = None
        search_results: list[dict] | None = None
        search_query: str = ""
        active_form = "request"

        if request.method == "POST":
            form_type = request.form.get("form_type", "request")
            active_form = "upload" if form_type == "upload" else "request"

            if form_type == "download":
                video_id = request.form.get("video_id", "").strip()
                video_url = request.form.get("video_url", "").strip()
                if not video_url and video_id:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                if video_url:
                    try:
                        out_path = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            yt_downloader
                        )(video_url, settings.base_download_dir)
                        result = {
                            "saved_path": str(out_path),
                            "download_href": url_for("download_file", file_path=str(out_path)),
                            "status": "Downloaded",
                        }
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("YouTube download failed")
                        error = str(exc)
                else:
                    error = "No video selected."
            elif active_form == "request":
                query = _build_search_query(
                    request.form.get("song_title", ""),
                    request.form.get("artist_name", ""),
                )
                if not query:
                    error = "Enter a song title, artist name, or both."
                else:
                    try:
                        results = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            search_youtube_songs
                        )(query, limit=5)
                        search_results = [
                            {
                                "video_id": r.video_id,
                                "url": r.url,
                                "title": r.title,
                                "uploader": r.uploader,
                                "duration": r.duration,
                                "duration_display": f"{r.duration // 60}:{(r.duration % 60):02d}" if r.duration else None,
                            }
                            for r in results
                        ]
                        search_query = query
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("YouTube search failed")
                        error = str(exc)
            else:
                file = request.files.get("screenshot")
                if file is None or not file.filename:
                    error = "Select an image file first."
                elif not _is_allowed_image(file.filename):
                    error = "Unsupported file type. Use png, jpg, jpeg, bmp, or webp."
                else:
                    safe_name = secure_filename(file.filename)
                    file_path = upload_dir / f"{uuid4().hex}_{safe_name}"
                    file.save(file_path)
                    try:
                        extract = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            extract_text_from_image
                        )
                        extracted_text = extract(file_path, settings.tesseract_psm)
                        guess = detect_song_and_artist(extracted_text)
                        query = _build_search_query(guess.title, guess.artist)
                        if not query:
                            error = "Could not detect song or artist from the image."
                        else:
                            results = retry(settings.max_retries, settings.retry_backoff_seconds)(
                                search_youtube_songs
                            )(query, limit=5)
                            search_results = [
                                {
                                    "video_id": r.video_id,
                                    "url": r.url,
                                    "title": r.title,
                                    "uploader": r.uploader,
                                    "duration": r.duration,
                                    "duration_display": f"{r.duration // 60}:{(r.duration % 60):02d}" if r.duration else None,
                                }
                                for r in results
                            ]
                            search_query = query
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Processing failed")
                        error = str(exc)
                    finally:
                        if file_path.exists():
                            file_path.unlink()

        return render_template(
            "index.html",
            error=error,
            result=result,
            search_results=search_results,
            search_query=search_query,
            active_form=active_form,
        )

    @app.route("/api/yt-search", methods=["GET"])
    def api_yt_search():
        query = request.args.get("query", "").strip()
        if not query:
            abort(400, description="Query parameter 'query' is required.")

        try:
            results = search_youtube_songs(query, limit=5)
        except Exception as exc:  # noqa: BLE001
            logger.exception("YouTube search failed")
            abort(500, description=str(exc))

        return jsonify({
            "items": [
                {
                    "video_id": r.video_id,
                    "url": r.url,
                    "title": r.title,
                    "uploader": r.uploader,
                    "duration": r.duration,
                }
                for r in results
            ]
        })

    @app.route("/api/yt-download", methods=["POST"])
    def api_yt_download():
        data = request.get_json(silent=True) or {}
        video_url = (data.get("video_url") or "").strip()
        video_id = (data.get("video_id") or "").strip()

        if not video_url and not video_id:
            abort(400, description="Provide either 'video_url' or 'video_id'.")

        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            out_path = yt_downloader(video_url, settings.base_download_dir)
        except Exception as exc:  # noqa: BLE001
            logger.exception("YouTube download failed")
            abort(500, description=str(exc))

        download_href = url_for("download_file", file_path=str(out_path))
        return jsonify({
            "saved_path": str(out_path),
            "download_href": download_href,
        })

    @app.route("/downloads/<path:file_path>", methods=["GET"])
    def download_file(file_path: str):
        try:
            resolved_path = _safe_download_path(file_path, settings.base_download_dir)
        except FileNotFoundError:
            abort(404)
        except PermissionError:
            abort(403)

        return send_file(resolved_path, as_attachment=True, download_name=resolved_path.name)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
