from __future__ import annotations

import os
import logging
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, jsonify, g, redirect, render_template, request, send_file, session, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Settings
from database import SessionLocal
from downloader import search_youtube_songs, yt_downloader
from repository import (
    create_user,
    create_download,
    create_song_request,
    get_song_request,
    get_user_by_id,
    get_user_by_username,
    list_active_admins,
    list_song_requests_for_admin,
    update_song_request,
)
from utils import ensure_directory, retry, setup_logging
from vision import detect_song_and_artist, extract_text_from_image

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
ROLE_REQUESTOR = "requestor"
ROLE_ADMIN = "admin"
SESSION_ROLE_KEY = "auth_role"
SESSION_USER_ID_KEY = "auth_user_id"
REQUEST_STATUSES = {"pending", "processing", "completed", "failed"}


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


def _session_role() -> str | None:
    role = (session.get(SESSION_ROLE_KEY) or "").strip().lower()
    return role if role in {ROLE_REQUESTOR, ROLE_ADMIN} else None


def _session_user_id() -> int | None:
    raw = session.get(SESSION_USER_ID_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _request_to_dict(row) -> dict:
    return {
        "request_id": str(row.id),
        "request_type": row.request_type.capitalize() if row.request_type else "",
        "song_title": row.song_title or "",
        "artist_name": row.artist_name or "",
        "extracted_text": row.extracted_text or "",
        "status": row.status or "",
        "created_time": row.created_at.isoformat(timespec="seconds") if row.created_at else "",
        "video_id": row.video_id or "",
        "video_url": row.video_url or "",
    }


def create_app() -> Flask:
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
    app.secret_key = os.getenv("MUSIC_AGENT_SECRET_KEY", "music-agent-dev-secret")

    upload_dir = Path("uploads")
    ensure_directory(upload_dir)

    @app.before_request
    def open_db_session() -> None:
        g.db = SessionLocal()

    @app.teardown_request
    def close_db_session(exc) -> None:  # noqa: ANN001
        db: Session | None = g.pop("db", None)
        if db is None:
            return
        try:
            if exc is None:
                db.commit()
            else:
                db.rollback()
        finally:
            db.close()
            SessionLocal.remove()

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        error: str | None = None
        success: str | None = None
        selected_role = ROLE_REQUESTOR
        signup_role = ROLE_REQUESTOR

        if request.method == "POST":
            db: Session = g.db
            action = (request.form.get("action") or "login").strip().lower()
            if action == "signup":
                signup_role = (request.form.get("signup_role") or ROLE_REQUESTOR).strip().lower()
                username = request.form.get("signup_username", "").strip()
                password = request.form.get("signup_password", "").strip()
                confirm_password = request.form.get("confirm_password", "").strip()

                if signup_role not in {ROLE_REQUESTOR, ROLE_ADMIN}:
                    error = "Invalid username/password or role"
                elif not username:
                    error = "Username is required."
                elif len(password) < 6:
                    error = "Password must be at least 6 characters."
                elif password != confirm_password:
                    error = "Password and confirm password do not match."
                elif get_user_by_username(db, username) is not None:
                    error = "Username already exists."
                else:
                    try:
                        user = create_user(
                            db,
                            username=username,
                            password_hash=generate_password_hash(password),
                            role=signup_role,
                            is_active=True,
                        )
                        session[SESSION_USER_ID_KEY] = user.id
                        session[SESSION_ROLE_KEY] = user.role
                        if user.role == ROLE_ADMIN:
                            return redirect(url_for("admin_page"))
                        return redirect(url_for("user_page"))
                    except IntegrityError:
                        db.rollback()
                        error = "Username already exists."
                    except Exception:  # noqa: BLE001
                        db.rollback()
                        logger.exception("Signup failed")
                        error = "Could not create account right now."
            else:
                selected_role = (request.form.get("role") or ROLE_REQUESTOR).strip().lower()
                username = request.form.get("username", "").strip()
                password = request.form.get("password", "").strip()

                user = get_user_by_username(db, username)
                if (
                    user
                    and user.is_active
                    and user.role == selected_role
                    and check_password_hash(user.password_hash, password)
                ):
                    session[SESSION_USER_ID_KEY] = user.id
                    session[SESSION_ROLE_KEY] = user.role
                    if user.role == ROLE_ADMIN:
                        return redirect(url_for("admin_page"))
                    return redirect(url_for("user_page"))
                error = "Invalid username/password or role"

        role = _session_role()
        if role == ROLE_ADMIN:
            return redirect(url_for("admin_page"))
        if role == ROLE_REQUESTOR:
            return redirect(url_for("user_page"))

        return render_template(
            "login.html",
            error=error,
            success=success,
            selected_role=selected_role,
            signup_role=signup_role,
        )

    @app.route("/logout")
    def logout():
        session.pop(SESSION_ROLE_KEY, None)
        session.pop(SESSION_USER_ID_KEY, None)
        return redirect(url_for("login_page"))

    @app.route("/")
    def index():
        role = _session_role()
        if role is None:
            return redirect(url_for("login_page"))
        if role == ROLE_ADMIN:
            return redirect(url_for("admin_page"))
        return redirect(url_for("user_page"))

    @app.route("/user", methods=["GET", "POST"])
    def user_page():
        role = _session_role()
        user_id = _session_user_id()
        if role is None or user_id is None:
            return redirect(url_for("login_page"))
        if role != ROLE_REQUESTOR:
            return redirect(url_for("admin_page"))

        db: Session = g.db
        error: str | None = None
        search_results: list[dict] | None = None
        search_query: str = ""
        active_form = "request"
        submission_message: str | None = None
        submission_request_id: str | None = None
        admins = list_active_admins(db)

        if request.method == "POST":
            form_type = request.form.get("form_type", "request")
            if form_type == "upload":
                active_form = "upload"
            else:
                active_form = "request"

            selected_admin_id_raw = request.form.get("assigned_admin_id", "").strip()
            try:
                selected_admin_id = int(selected_admin_id_raw)
            except ValueError:
                selected_admin_id = 0

            admin = get_user_by_id(db, selected_admin_id)
            if admin is None or admin.role != ROLE_ADMIN or not admin.is_active:
                error = "Select a valid admin."
            elif form_type == "request_select":
                request_id_raw = request.form.get("request_id", "").strip()
                video_id = request.form.get("video_id", "").strip()
                video_url = request.form.get("video_url", "").strip()
                selected_title = request.form.get("selected_title", "").strip()
                selected_artist = request.form.get("selected_artist", "").strip()
                try:
                    request_id = int(request_id_raw)
                except ValueError:
                    request_id = 0

                row = get_song_request(db, request_id) if request_id else None
                if row is None or row.requestor_id != user_id:
                    error = "Invalid request selection."
                elif not (video_id or video_url):
                    error = "No video selected."
                else:
                    update_song_request(
                        row,
                        video_id=video_id or None,
                        video_url=video_url or None,
                        song_title=selected_title or None,
                        artist_name=selected_artist or None,
                        assigned_admin_id=admin.id,
                        status="pending",
                    )
                    submission_request_id = str(row.id)
                    submission_message = "Request submitted successfully"
            elif active_form == "request":
                song_title = request.form.get("song_title", "").strip()
                artist_name = request.form.get("artist_name", "").strip()
                query = _build_search_query(song_title, artist_name)
                row = create_song_request(
                    db,
                    requestor_id=user_id,
                    assigned_admin_id=admin.id,
                    request_type="text",
                    song_title=song_title or None,
                    artist_name=artist_name or None,
                    status="pending",
                )
                submission_request_id = str(row.id)
                if not query:
                    error = "Enter a song title, artist name, or both."
                    update_song_request(row, status="failed")
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
                                "request_id": str(row.id),
                                "assigned_admin_id": str(admin.id),
                            }
                            for r in results
                        ]
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("YouTube search failed")
                        error = str(exc)
                        update_song_request(row, status="failed")
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
                    row = create_song_request(
                        db,
                        requestor_id=user_id,
                        assigned_admin_id=admin.id,
                        request_type="screenshot",
                        status="processing",
                    )
                    submission_request_id = str(row.id)
                    try:
                        extract = retry(settings.max_retries, settings.retry_backoff_seconds)(
                            extract_text_from_image
                        )
                        extracted_text = extract(file_path, settings.tesseract_psm)
                        guess = detect_song_and_artist(extracted_text)
                        update_song_request(
                            row,
                            song_title=guess.title or None,
                            artist_name=guess.artist or None,
                            extracted_text=extracted_text,
                        )
                        query = _build_search_query(guess.title, guess.artist)
                        if not query:
                            error = "Could not detect song or artist from the image."
                            update_song_request(row, status="failed")
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
                                    "request_id": str(row.id),
                                    "assigned_admin_id": str(admin.id),
                                }
                                for r in results
                            ]
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Processing failed")
                        error = str(exc)
                        update_song_request(row, status="failed")
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
            admins=admins,
            role=role,
        )

    @app.route("/admin", methods=["GET", "POST"])
    def admin_page():
        role = _session_role()
        user_id = _session_user_id()
        if role is None or user_id is None:
            return redirect(url_for("login_page"))
        if role != ROLE_ADMIN:
            return redirect(url_for("user_page"))

        db: Session = g.db
        error: str | None = None
        result: dict | None = None
        if request.method == "POST":
            form_type = request.form.get("form_type", "").strip()
            if form_type == "download":
                request_id_raw = request.form.get("request_id", "").strip()
                try:
                    request_id = int(request_id_raw)
                except ValueError:
                    request_id = 0

                row = get_song_request(db, request_id) if request_id else None
                if row is None or row.assigned_admin_id != user_id:
                    error = "Invalid request."
                else:
                    video_id = (row.video_id or "").strip()
                    video_url = (row.video_url or "").strip()
                    if not video_url and video_id:
                        video_url = f"https://www.youtube.com/watch?v={video_id}"

                    if not video_url:
                        query = _build_search_query(row.song_title or "", row.artist_name or "")
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
                                    update_song_request(row, video_id=video_id, video_url=video_url)
                            except Exception as exc:  # noqa: BLE001
                                logger.exception("YouTube search failed")
                                error = str(exc)
                    if not error and video_url:
                        try:
                            update_song_request(row, status="processing")
                            out_path = retry(settings.max_retries, settings.retry_backoff_seconds)(
                                yt_downloader
                            )(video_url, settings.base_download_dir)
                            result = {
                                "saved_path": str(out_path),
                                "download_href": url_for("download_file", file_path=str(out_path)),
                                "status": "Downloaded",
                            }
                            update_song_request(row, status="completed")
                            create_download(
                                db,
                                request_id=row.id,
                                admin_id=user_id,
                                saved_path=str(out_path),
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("YouTube download failed")
                            error = str(exc)
                            update_song_request(row, status="failed")

        requests_data = [_request_to_dict(row) for row in list_song_requests_for_admin(db, user_id)]
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
