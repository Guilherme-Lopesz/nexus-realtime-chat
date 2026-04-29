"""
utils.py — Utilitários gerais compartilhados.
"""

from __future__ import annotations

import os
from datetime import datetime

from extensions import socketio
from state import online_users, room_admins, room_users

# ---------------------------------------------------------------------------
# Constantes de arquivo
# ---------------------------------------------------------------------------

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif"}
AUDIO_EXTS = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".opus", ".flac", ".aac"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v"}

EMOJI_MAP: dict[str, str] = {
    ":)": "😊", ":-)": "😊", ":D": "😄", ":-D": "😄",
    ":(": "😢", ":-(": "😢", ";)": "😉", ";-)": "😉",
    ":P": "😛", ":-P": "😛", ":O": "😮", ":-O": "😮",
    ">:(": "😠", ":'(": "😭", "<3": "❤️", "</3": "💔",
    ":*": "😘", "B)": "😎", ":|": "😐", ":think:": "🤔",
    ":fire:": "🔥", ":ok:": "👌", ":wave:": "👋", ":clap:": "👏",
    ":+1:": "👍", ":-1:": "👎", ":100:": "💯", ":star:": "⭐",
}


# ---------------------------------------------------------------------------
# Helpers de texto
# ---------------------------------------------------------------------------

def now_str() -> str:
    return datetime.now().strftime("%H:%M")


def replace_emojis(text: str) -> str:
    for code, emoji in EMOJI_MAP.items():
        text = text.replace(code, emoji)
    return text


def file_type_from_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "file"


# ---------------------------------------------------------------------------
# Emissão de mensagens
# ---------------------------------------------------------------------------

def system_msg(room: str, text: str) -> None:
    """Envia mensagem de sistema para uma sala."""
    socketio.emit(
        "system_message",
        {"msg": text, "type": "system", "time": now_str()},
        to=room,
    )


def get_rooms_list() -> list[dict]:
    """Retorna lista de salas formatada para o cliente."""
    from models import Room

    try:
        rooms = Room.query.order_by(Room.last_activity.desc()).all()
        result = []
        for r in rooms:
            users_count = sum(
                1 for u in online_users.values() if u.get("room") == r.name
            )
            result.append(
                {
                    "name": r.name,
                    "description": r.description or "",
                    "users": users_count,
                    "max": r.max_users,
                    "private": r.is_private,
                    "last_activity": (
                        r.last_activity.strftime("%H:%M") if r.last_activity else "N/A"
                    ),
                    "created_by": r.created_by,
                }
            )
        return result
    except Exception as exc:
        import logging
        logging.getLogger("nexus").error("Erro ao obter lista de salas: %s", exc)
        return []


def update_room_users(room: str) -> None:
    """Sincroniza lista de usuários na sala e emite para todos."""
    users = [u["username"] for u in online_users.values() if u.get("room") == room]
    room_users[room] = users
    socketio.emit(
        "user_list",
        {"room": room, "users": users, "count": len(users)},
        to=room,
    )


def touch_room(room_name: str) -> None:
    """Atualiza last_activity da sala no banco."""
    from datetime import timezone
    from models import Room
    from extensions import db

    room_obj = Room.query.filter_by(name=room_name).first()
    if room_obj:
        room_obj.last_activity = datetime.now(timezone.utc)
        db.session.commit()


# ---------------------------------------------------------------------------
# Helpers de busca de usuários
# ---------------------------------------------------------------------------

def find_sid(username: str, room: str) -> str | None:
    """Retorna SID do usuário em uma sala específica."""
    return next(
        (s for s, u in online_users.items()
         if u["username"] == username and u.get("room") == room),
        None,
    )


def find_sid_global(username: str) -> str | None:
    """Retorna SID do usuário em qualquer sala."""
    return next(
        (s for s, u in online_users.items() if u["username"] == username),
        None,
    )


def user_in_room(username: str, room: str) -> bool:
    return any(
        u["username"] == username and u.get("room") == room
        for u in online_users.values()
    )


def build_message_payload(msg, user_info: dict, room: str) -> dict:
    """Constrói payload padrão de mensagem a partir de um objeto Message."""
    is_admin = msg.username in room_admins[room] or user_info.get("role") == "admin"
    can_delete = (
        msg.user_id == user_info.get("user_id")
        or is_admin
    )
    return {
        "id": msg.id,
        "user": msg.username,
        "text": msg.content,
        "type": msg.content_type,
        "url": msg.file_url,
        "time": msg.timestamp.strftime("%H:%M"),
        "role": "admin" if is_admin else "user",
        "timestamp": msg.timestamp.isoformat(),
        "reply_to": msg.reply_to,
        "can_delete": can_delete,
    }
