"""
antispam.py — Anti-spam, rate limiting e verificação de banimento.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from state import (
    ip_message_counts,
    muted_users,
    user_last_message,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SPAM_WINDOW = 5           # segundos
SPAM_MSG_LIMIT = 8        # msgs por janela por usuário
SPAM_FILE_WINDOW = 30
SPAM_FILE_LIMIT = 3
SPAM_MUTE_DURATION = 300  # 5 min

IP_WINDOW = 10            # segundos
IP_MSG_LIMIT = 20         # msgs por janela por IP (global)


# ---------------------------------------------------------------------------
# Anti-spam por usuário
# ---------------------------------------------------------------------------

def check_spam(username: str, room: str, *, is_file: bool = False) -> tuple[bool, str]:
    """
    Verifica limite de mensagens/arquivos por usuário.
    Retorna (permitido, motivo).
    """
    now = time.time()
    key = f"{username}:{room}"

    if key not in user_last_message:
        user_last_message[key] = {
            "time": now, "count": 1,
            "file_time": now, "file_count": 0,
        }
        return True, ""

    data = user_last_message[key]

    if is_file:
        if now - data["file_time"] < SPAM_FILE_WINDOW:
            data["file_count"] += 1
            if data["file_count"] > SPAM_FILE_LIMIT:
                _apply_auto_mute(username, room, "Spam de arquivos")
                return False, "Spam de arquivos detectado."
        else:
            data["file_time"] = now
            data["file_count"] = 1
        return True, ""

    if now - data["time"] > SPAM_WINDOW:
        data["time"] = now
        data["count"] = 1
    else:
        data["count"] += 1
        if data["count"] > SPAM_MSG_LIMIT:
            _apply_auto_mute(username, room, "Spam de mensagens")
            return False, "Spam detectado. Você foi mutado por 5 minutos."

    return True, ""


def check_ip_rate(ip: str) -> bool:
    """
    Verifica limite global por IP.
    Retorna True se permitido.
    """
    now = time.time()
    if ip not in ip_message_counts:
        ip_message_counts[ip] = {"time": now, "count": 1}
        return True

    data = ip_message_counts[ip]
    if now - data["time"] > IP_WINDOW:
        data["time"] = now
        data["count"] = 1
    else:
        data["count"] += 1
        if data["count"] > IP_MSG_LIMIT:
            return False
    return True


def _apply_auto_mute(username: str, room: str, reason: str) -> None:
    muted_users[username] = {
        "until": time.time() + SPAM_MUTE_DURATION,
        "reason": reason,
        "by": "Sistema",
    }
    # Importação tardia para evitar circular
    from utils import system_msg
    system_msg(room, f"🔇 {username} foi mutado automaticamente por 5 minutos: {reason}.")


def check_mute(username: str, room: str) -> tuple[bool, int]:
    """
    Verifica se o usuário está mutado.
    Retorna (mutado, segundos_restantes).
    """
    if username not in muted_users:
        return False, 0

    mute = muted_users[username]
    remaining = int(mute["until"] - time.time())

    if remaining <= 0:
        del muted_users[username]
        from utils import system_msg
        system_msg(room, f"🎤 {username} não está mais mutado.")
        return False, 0

    return True, remaining


# ---------------------------------------------------------------------------
# Verificação de ban no banco
# ---------------------------------------------------------------------------

def is_banned(username: str | None, ip: str | None) -> tuple[bool, str]:
    """
    Verifica se usuário ou IP está banido.
    Retorna (banido, motivo).
    """
    from models import Ban

    now = datetime.now(timezone.utc)

    query_filters = []
    if username:
        query_filters.append(Ban.username == username)
    if ip:
        query_filters.append(Ban.ip_address == ip)

    if not query_filters:
        return False, ""

    from sqlalchemy import or_
    bans = Ban.query.filter(or_(*query_filters)).all()

    for ban in bans:
        if ban.is_active:
            expires = (
                ban.expires_at.strftime("%d/%m/%Y %H:%M")
                if ban.expires_at
                else "permanente"
            )
            return True, f"Banido por: {ban.reason} (expira: {expires})"

    return False, ""


def cleanup_spam_data(username: str) -> None:
    """Remove dados de anti-spam de um usuário que desconectou."""
    keys = [k for k in user_last_message if k.startswith(f"{username}:")]
    for key in keys:
        user_last_message.pop(key, None)