from __future__ import annotations

import os
import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from config import Settings
from downloader import search_youtube_songs, yt_downloader
from utils import ensure_directory, retry, setup_logging
from vision import detect_song_and_artist, extract_text_from_image

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
ROLE_USER = "user"
ROLE_ADMIN = "admin"
REQUEST_STATUSES = {"pending", "processing", "completed", "failed"}

_request_store: list[dict] = []
_request_store_lock = Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def _resolve_role() -> str:
    role = (request.args.get("role") or request.headers.get("X-Role") or "").strip().lower()
    if role in {ROLE_USER, ROLE_ADMIN}:
        return role

    env_role = os.getenv("MUSIC_AGENT_DEFAULT_ROLE", ROLE_USER).strip().lower()
    if env_role in {ROLE_USER, ROLE_ADMIN}:
        return env_role
    return ROLE_USER


def _create_submission(
    *,
    request_type: str,
    song_title: str | None = None,
    artist_name: str | None = None,
    extracted_text: str | None = None,
    status: str = "pending",
    video_id: str | None = None,
    video_url: str | None = None,
) -> dict:
    normalized_status = status if status in REQUEST_STATUSES else "pending"
    submission = {
        "request_id": uuid4().hex[:12],
        "request_type": request_type,
        "song_title": song_title or "",
        "artist_name": artist_name or "",
        "extracted_text": extracted_text or "",
        "status": normalized_status,
        "created_time": _now_iso(),
        "video_id": video_id or "",
        "video_url": video_url or "",
    }
    with _request_store_lock:
        _request_store.append(submission)
    return submission


def _update_submission(request_id: str, **updates: str) -> None:
    with _request_store_lock:
        for item in _request_store:
            if item["request_id"] != request_id:
                continue
            if "status" in updates:
                status = (updates.get("status") or "").strip().lower()
                if status in REQUEST_STATUSES:
                    item["status"] = status
            if "song_title" in updates and updates["song_title"] is not None:
                item["song_title"] = updates["song_title"]
            if "artist_name" in updates and updates["artist_name"] is not None:
                item["artist_name"] = updates["artist_name"]
            if "extracted_text" in updates and updates["extracted_text"] is not None:
                item["extracted_text"] = updates["extracted_text"]
            if "video_id" in updates and updates["video_id"] is not None:
                item["video_id"] = updates["video_id"]
            if "video_url" in updates and updates["video_url"] is not None:
                item["video_url"] = updates["video_url"]
            break


def _list_submissions() -> list[dict]:
    with _request_store_lock:
        return list(reversed(_request_store))


def _get_submission(request_id: str) -> dict | None:
    with _request_store_lock:
        for item in _request_store:
            if item.get("request_id") == request_id:
                return dict(item)
    return None


def create_app() -> Flask:
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

    upload_dir = Path("uploads")
    ensure_directory(upload_dir)

    @app.route("/")
    def index():
        role = _resolve_role()
        if role == ROLE_ADMIN:
            return redirect(url_for("admin_page", role=ROLE_ADMIN))
        return redirect(url_for("user_page", role=ROLE_USER))

    @app.route("/user", methods=["GET", "POST"])
    def user_page():
        error: str | None = None
        search_results: list[dict] | None = None
        search_query: str = ""
        active_form = "request"
        submission_message: str | None = None
        submission_request_id: str | None = None

        if request.method == "POST":
            form_type = request.form.get("form_type", "request")
            if form_type == "upload":
                active_form = "upload"
            elif form_type == "request_select":
                active_form = "request"
            else:
                active_form = "request"

            if form_type == "request_select":
                request_id = request.form.get("request_id", "").strip()
                video_id = request.form.get("video_id", "").strip()
                video_url = request.form.get("video_url", "").strip()
                selected_title = request.form.get("selected_title", "").strip()
                selected_artist = request.form.get("selected_artist", "").strip()
                if request_id and (video_id or video_url):
                    _update_submission(
                        request_id,
                        video_id=video_id,
                        video_url=video_url,
                        song_title=selected_title or None,
                        artist_name=selected_artist or None,
                        status="pending",
                    )
                    submission_request_id = request_id
                    submission_message = "Request submitted successfully"
                else:
                    error = "No video selected."
            elif active_form == "request":
                song_title = request.form.get("song_title", "").strip()
                artist_name = request.form.get("artist_name", "").strip()
                query = _build_search_query(song_title, artist_name)
                submission = _create_submission(
                    request_type="Text",
                    song_title=song_title,
                    artist_name=artist_name,
                    status="pending",
                )
                submission_request_id = submission["request_id"]
                if not query:
                    error = "Enter a song title, artist name, or both."
                    _update_submission(submission_request_id, status="failed")
                else:
                    try:
                        results = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            search_youtube_songs
                        )(query, limit=5)
                        search_query = query
                        search_results = [
                            {
                                "video_id": r.video_id,
                                "url": r.url,
                                "title": r.title,
                                "uploader": r.uploader,
                                "duration": r.duration,
                                "duration_display": f"{r.duration // 60}:{(r.duration % 60):02d}" if r.duration else None,
                                "request_id": submission_request_id,
                            }
                            for r in results
                        ]
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("YouTube search failed")
                        error = str(exc)
                        _update_submission(submission_request_id, status="failed")
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
                    submission = _create_submission(request_type="Screenshot", status="processing")
                    submission_request_id = submission["request_id"]
                    try:
                        extract = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            extract_text_from_image
                        )
                        extracted_text = extract(file_path, settings.tesseract_psm)
                        guess = detect_song_and_artist(extracted_text)
                        _update_submission(
                            submission_request_id,
                            song_title=guess.title,
                            artist_name=guess.artist,
                            extracted_text=extracted_text,
                        )
                        query = _build_search_query(guess.title, guess.artist)
                        if not query:
                            error = "Could not detect song or artist from the image."
                            _update_submission(submission_request_id, status="failed")
                        else:
                            results = retry(settings.max_retries, settings.retry_backoff_seconds)(
                                search_youtube_songs
                            )(query, limit=5)
                            search_query = query
                            search_results = [
                                {
                                    "video_id": r.video_id,
                                    "url": r.url,
                                    "title": r.title,
                                    "uploader": r.uploader,
                                    "duration": r.duration,
                                    "duration_display": f"{r.duration // 60}:{(r.duration % 60):02d}" if r.duration else None,
                                    "request_id": submission_request_id,
                                }
                                for r in results
                            ]
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Processing failed")
                        error = str(exc)
                        _update_submission(submission_request_id, status="failed")
                    finally:
                        if file_path.exists():
                            file_path.unlink()

        return render_template(
            "user.html",
            error=error,
            search_results=search_results,
            search_query=search_query,
            active_form=active_form,
            submission_message=submission_message,
            submission_request_id=submission_request_id,
            role=_resolve_role(),
        )

    @app.route("/admin", methods=["GET", "POST"])
    def admin_page():
        role = _resolve_role()
        if role != ROLE_ADMIN:
            return redirect(url_for("user_page", role=ROLE_USER))

        error: str | None = None
        result: dict | None = None
        if request.method == "POST":
            form_type = request.form.get("form_type", "").strip()
            if form_type == "download":
                request_id = request.form.get("request_id", "").strip()
                video_id = request.form.get("video_id", "").strip()
                video_url = request.form.get("video_url", "").strip()
                submission = _get_submission(request_id) if request_id else None
                if not video_id and submission:
                    video_id = (submission.get("video_id") or "").strip()
                if not video_url and submission:
                    video_url = (submission.get("video_url") or "").strip()
                if not video_url and video_id:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"

                if not video_url:
                    song_title = (submission or {}).get("song_title", "")
                    artist_name = (submission or {}).get("artist_name", "")
                    query = _build_search_query(song_title, artist_name)
                    if not query:
                        error = "No video selected."
                    else:
                        try:
                            results = retry(settings.max_retries, settings.retry_backoff_seconds)(
                                search_youtube_songs
                            )(query, limit=1)
                            if not results:
                                error = f"No YouTube results for: {query}"
                            else:
                                top = results[0]
                                video_id = top.video_id
                                video_url = top.url
                                if request_id:
                                    _update_submission(request_id, video_id=video_id, video_url=video_url)
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("YouTube search failed")
                            error = str(exc)
                if not error and video_url:
                    try:
                        if request_id:
                            _update_submission(request_id, status="processing")
                        out_path = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            yt_downloader
                        )(video_url, settings.base_download_dir)
                        result = {
                            "saved_path": str(out_path),
                            "download_href": url_for("download_file", file_path=str(out_path)),
                            "status": "Downloaded",
                        }
                        if request_id:
                            _update_submission(request_id, status="completed")
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("YouTube download failed")
                        error = str(exc)
                        if request_id:
                            _update_submission(request_id, status="failed")

        requests_data = _list_submissions()
        visible_columns = {
            "request_id": any(item.get("request_id") for item in requests_data),
            "request_type": any(item.get("request_type") for item in requests_data),
            "song_title": any(item.get("song_title") for item in requests_data),
            "artist_name": any(item.get("artist_name") for item in requests_data),
            "extracted_text": any(item.get("extracted_text") for item in requests_data),
            "status": any(item.get("status") for item in requests_data),
            "created_time": any(item.get("created_time") for item in requests_data),
            "download": bool(requests_data),
        }

        return render_template(
            "admin.html",
            error=error,
            result=result,
            requests_data=requests_data,
            visible_columns=visible_columns,
            role=role,
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
