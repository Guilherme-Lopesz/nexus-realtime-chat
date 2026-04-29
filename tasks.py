"""
tasks.py — Tarefas de background (threads daemon).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from extensions import socketio
from state import (
    guest_warnings_sent,
    online_users,
    room_users,
    typing_users,
    visitors,
)
from utils import system_msg, update_room_users

GUEST_SESSION_LIMIT = 900      # 15 min
GUEST_WARNING_THRESHOLD = 120  # avisa quando restam 2 min
INACTIVE_ROOM_MINUTES = 60     # salas sem usuários por 60 min são limpas


# ---------------------------------------------------------------------------
# Monitor de tempo de guest
# ---------------------------------------------------------------------------

def check_guest_time() -> None:
    """Loop infinito que monitora o tempo de sessão dos guests."""
    while True:
        time.sleep(30)
        now = time.time()

        for sid, start_time in list(visitors.items()):
            elapsed = now - start_time
            remaining = GUEST_SESSION_LIMIT - elapsed

            # Aviso de 2 minutos
            if GUEST_WARNING_THRESHOLD <= remaining <= GUEST_WARNING_THRESHOLD + 30:
                if sid not in guest_warnings_sent and sid in online_users:
                    socketio.emit(
                        "guest_warning",
                        {
                            "msg": "⚠️ Você tem apenas 2 minutos restantes. "
                                   "Crie uma conta para continuar sem limites!",
                            "time": 10,
                        },
                        to=sid,
                    )
                    guest_warnings_sent.add(sid)

            # Tempo esgotado
            elif elapsed >= GUEST_SESSION_LIMIT:
                if sid in online_users:
                    user_info = online_users[sid]
                    room = user_info.get("room")

                    socketio.emit(
                        "force_kick",
                        {
                            "reason": (
                                "Tempo limite de 15 minutos excedido. "
                                "Faça login ou registre-se para continuar."
                            )
                        },
                        to=sid,
                    )

                    if room:
                        system_msg(
                            room,
                            f"⏰ {user_info['username']} foi desconectado (limite de guest).",
                        )
                        from flask_socketio import leave_room as _leave
                        room_users[room] = [
                            u for u in room_users[room]
                            if u != user_info["username"]
                        ]
                        update_room_users(room)

                    online_users.pop(sid, None)

                visitors.pop(sid, None)
                guest_warnings_sent.discard(sid)


# ---------------------------------------------------------------------------
# Limpeza de salas inativas
# ---------------------------------------------------------------------------

def cleanup_inactive_rooms() -> None:
    """
    Loop infinito que remove salas sem atividade por mais de INACTIVE_ROOM_MINUTES.
    Apenas salas cujo criador foi 'Guest' (sem dono registrado) são removidas.
    """
    while True:
        time.sleep(300)  # verifica a cada 5 minutos
        from models import Room
        from extensions import db

        cutoff = datetime.now(timezone.utc).timestamp() - INACTIVE_ROOM_MINUTES * 60

        try:
            with db.engine.connect():
                rooms = Room.query.filter(Room.owner_id.is_(None)).all()
                for room in rooms:
                    if not room.last_activity:
                        continue
                    room_ts = room.last_activity.timestamp()
                    active_users = sum(
                        1 for u in online_users.values() if u.get("room") == room.name
                    )
                    if room_ts < cutoff and active_users == 0:
                        db.session.delete(room)
                db.session.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Limpeza de typing indicators
# ---------------------------------------------------------------------------

def cleanup_typing() -> None:
    """
    Limpa indicadores de digitação para usuários offline.
    Previne que o indicador fique preso.
    """
    while True:
        time.sleep(10)
        online_names = {u["username"] for u in online_users.values()}
        for room_name, typists in list(typing_users.items()):
            before = len(typists)
            typists -= typists - (typists & online_names)
            if len(typists) != before:
                socketio.emit(
                    "typing_update",
                    {"users": list(typists)},
                    to=room_name,
                )
