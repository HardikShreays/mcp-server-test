from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Download, SongRequest, User


def list_active_admins(db: Session) -> list[User]:
    stmt = (
        select(User)
        .where(User.role == "admin", User.is_active.is_(True))
        .order_by(User.username.asc())
    )
    return list(db.scalars(stmt))


def get_user_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.scalars(stmt).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(
    db: Session,
    *,
    username: str,
    password_hash: str,
    role: str,
    is_active: bool = True,
) -> User:
    row = User(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def create_song_request(
    db: Session,
    *,
    requestor_id: int,
    assigned_admin_id: int,
    request_type: str,
    song_title: str | None = None,
    artist_name: str | None = None,
    extracted_text: str | None = None,
    status: str = "pending",
) -> SongRequest:
    row = SongRequest(
        requestor_id=requestor_id,
        assigned_admin_id=assigned_admin_id,
        request_type=request_type,
        song_title=song_title,
        artist_name=artist_name,
        extracted_text=extracted_text,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


def get_song_request(db: Session, request_id: int) -> SongRequest | None:
    return db.get(SongRequest, request_id)


def list_song_requests_for_admin(db: Session, admin_id: int) -> list[SongRequest]:
    stmt = (
        select(SongRequest)
        .where(SongRequest.assigned_admin_id == admin_id)
        .order_by(SongRequest.created_at.desc(), SongRequest.id.desc())
    )
    return list(db.scalars(stmt))


def update_song_request(row: SongRequest, **updates: Any) -> SongRequest:
    for key, value in updates.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    return row


def create_download(db: Session, *, request_id: int, admin_id: int, saved_path: str) -> Download:
    row = Download(request_id=request_id, admin_id=admin_id, saved_path=saved_path)
    db.add(row)
    db.flush()
    return row
