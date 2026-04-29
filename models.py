"""
models.py — Modelos SQLAlchemy do Nexus Chat.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import bcrypt, db


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warnings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bio: Mapped[str | None] = mapped_column(String(256), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(64), nullable=True)   # emoji ou URL
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="author")
    owned_rooms: Mapped[list["Room"]] = relationship("Room", back_populates="owner")

    def set_password(self, raw: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, raw)

    @property
    def role(self) -> str:
        return "admin" if self.is_admin else "user"

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "is_admin": self.is_admin,
            "avatar": self.avatar or "👤",
            "bio": self.bio or "",
            "warnings": self.warnings,
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

class Room(db.Model):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    max_users: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="Guest", nullable=False)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    owner: Mapped[User | None] = relationship("User", back_populates="owned_rooms")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="room_rel")

    def set_password(self, raw: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw: str) -> bool:
        if not self.password_hash:
            return True
        return bcrypt.check_password_hash(self.password_hash, raw)

    @property
    def is_private(self) -> bool:
        return self.password_hash is not None


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class Message(db.Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    room_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), default="text")
    file_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reply_to: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    author: Mapped[User | None] = relationship("User", back_populates="messages")
    room_rel: Mapped[Room] = relationship("Room", back_populates="messages")


# ---------------------------------------------------------------------------
# Ban
# ---------------------------------------------------------------------------

class Ban(db.Model):
    __tablename__ = "bans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(256), default="Violação das regras")
    banned_by: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True   # None = permanente
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_active(self) -> bool:
        if self.expires_at is None:
            return True
        return datetime.now(timezone.utc) < self.expires_at