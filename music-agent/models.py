from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    requested_songs: Mapped[list["SongRequest"]] = relationship(
        foreign_keys="SongRequest.requestor_id",
        back_populates="requestor",
    )
    assigned_songs: Mapped[list["SongRequest"]] = relationship(
        foreign_keys="SongRequest.assigned_admin_id",
        back_populates="assigned_admin",
    )


class SongRequest(Base):
    __tablename__ = "song_requests"
    __table_args__ = (
        Index("ix_song_requests_assigned_admin_id_created_at", "assigned_admin_id", "created_at"),
        Index("ix_song_requests_requestor_id_created_at", "requestor_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requestor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assigned_admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    song_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artist_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    requestor: Mapped[User] = relationship(foreign_keys=[requestor_id], back_populates="requested_songs")
    assigned_admin: Mapped[User] = relationship(
        foreign_keys=[assigned_admin_id],
        back_populates="assigned_songs",
    )
    downloads: Mapped[list["Download"]] = relationship(back_populates="request")


class Download(Base):
    __tablename__ = "downloads"
    __table_args__ = (Index("ix_downloads_request_id_created_at", "request_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("song_requests.id"), nullable=False, index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    saved_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    request: Mapped[SongRequest] = relationship(back_populates="downloads")
    admin: Mapped[User] = relationship()

