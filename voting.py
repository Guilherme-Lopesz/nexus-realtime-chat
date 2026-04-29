"""
voting.py — Lógica de votação (votekick / votemute).
"""

from __future__ import annotations

import time

from extensions import socketio
from state import muted_users, online_users, room_locks, room_votes
from utils import system_msg


def vote_timer(room: str) -> None:
    """Background task: aguarda 60s e resolve a votação."""
    time.sleep(60)
    _vote_resolve(room)


def _vote_resolve(room: str) -> None:
    """Resolve a votação ao fim do timer."""
    with room_locks[room]:
        if room not in room_votes:
            return

        vote = room_votes[room]
        yes_count = len(vote["yes"])
        no_count = len(vote["no"])
        total = yes_count + no_count
        room_user_count = sum(
            1 for u in online_users.values() if u.get("room") == room
        )

        def finish(result: str, success: bool) -> None:
            system_msg(room, result)
            socketio.emit(
                "vote_update",
                {"type": "result", "result": result, "success": success},
                to=room,
            )
            room_votes.pop(room, None)

        if total == 0:
            finish("📊 Votação cancelada (nenhum voto).", False)
            return

        if room_user_count > 3 and total < 3:
            finish("❌ Votação falhou (quórum insuficiente).", False)
            return

        if yes_count <= no_count:
            finish("❌ Votação rejeitada pela maioria.", False)
            return

        # Aprovada
        target = vote["target"]
        v_type = vote["type"]

        if v_type == "kick":
            target_sid = next(
                (s for s, u in online_users.items()
                 if u["username"] == target and u.get("room") == room),
                None,
            )
            if target_sid:
                socketio.emit(
                    "force_kick",
                    {"reason": "Expulso por votação da comunidade."},
                    to=target_sid,
                )
                finish(f"✅ {target} foi expulso por votação.", True)
            else:
                finish(f"✅ Votação aprovada, mas {target} já saiu.", False)

        elif v_type == "mute":
            minutes = vote.get("minutes", 10)
            muted_users[target] = {
                "until": time.time() + minutes * 60,
                "reason": f"Mutado por votação (iniciado por {vote['started_by']})",
                "by": "Comunidade",
            }
            finish(f"✅ {target} foi mutado por {minutes} minutos por votação.", True)
