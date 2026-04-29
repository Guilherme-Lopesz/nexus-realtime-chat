"""
commands.py — Processamento de comandos de chat (/kick, /ban, /clear, …).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from extensions import db, socketio
from models import Ban, Message, Room, User
from state import (
    muted_users,
    online_users,
    private_chat_enabled,
    room_admins,
    room_votes,
    warning_log,
)
from utils import (
    find_sid,
    find_sid_global,
    now_str,
    replace_emojis,
    system_msg,
    update_room_users,
    user_in_room,
)
from voting import vote_timer

# ---------------------------------------------------------------------------
# Texto de ajuda
# ---------------------------------------------------------------------------

HELP_TEXT = """
📋 <b>COMANDOS DISPONÍVEIS:</b>

👤 <b>Todos:</b>
  /pm &lt;user&gt; &lt;msg&gt;              — Mensagem privada
  /togglepm                       — Ativa/desativa PMs recebidas
  /votekick &lt;user&gt;               — Inicia votação para expulsar
  /votemute &lt;user&gt; [min]         — Inicia votação para mutar
  /sim  /não                      — Votar na votação ativa
  /emojis                         — Lista de emojis disponíveis

👑 <b>Admin / Dono da sala:</b>
  /kick &lt;user&gt; [razão]           — Expulsar usuário
  /warn &lt;user&gt; [razão]           — Advertir usuário
  /mute &lt;user&gt; [min] [razão]     — Mutar usuário
  /unmute &lt;user&gt;                  — Desmutar usuário
  /ban &lt;user&gt; [dias] [razão]     — Banir usuário (0 = permanente)
  /clear                          — Limpar mensagens da sala
  /roomdesc &lt;texto&gt;              — Definir descrição da sala
  /broadcast &lt;msg&gt;               — Anunciar para todos

💡 Use :código: para emojis — ex: <b>:)</b> → 😊
"""


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------

def handle_command(sid: str, room: str, msg: str) -> None:
    user_info = online_users.get(sid)
    if not user_info:
        return

    username: str = user_info["username"]
    role: str = user_info["role"]

    parts = msg.strip().split(" ")
    cmd = parts[0].lower()
    args = parts[1:]

    room_obj = Room.query.filter_by(name=room).first()
    is_admin = username in room_admins[room] or role == "admin"
    is_owner = bool(room_obj and room_obj.owner_id == user_info.get("user_id"))
    is_privileged = is_admin or is_owner

    def err(text: str) -> None:
        socketio.emit("error", {"msg": text}, to=sid)

    def sys(text: str) -> None:
        system_msg(room, text)

    # ---- /kick ----
    if cmd == "/kick":
        if not is_privileged:
            return err("Você não tem permissão para usar /kick.")
        if not args:
            return err("Uso: /kick <usuário> [razão]")
        target, reason = args[0], " ".join(args[1:]) or "Sem razão especificada"
        t_sid = find_sid(target, room)
        if t_sid:
            sys(f"🚫 {target} foi expulso por {username}. Razão: {reason}")
            socketio.emit("force_kick", {"reason": f"Expulso por {username}: {reason}"}, to=t_sid)
        else:
            err(f"Usuário {target} não encontrado na sala.")

    # ---- /warn ----
    elif cmd == "/warn":
        if not is_privileged:
            return err("Você não tem permissão para usar /warn.")
        if not args:
            return err("Uso: /warn <usuário> [razão]")
        target, reason = args[0], " ".join(args[1:]) or "Aviso do administrador"
        warning_log[target].append({"reason": reason, "by": username, "time": time.time()})
        user_db = User.query.filter_by(username=target).first()
        if user_db:
            user_db.warnings += 1
            db.session.commit()
        sys(f"⚠️ {target} recebeu um aviso de {username}. Razão: {reason}")
        t_sid = find_sid(target, room)
        if t_sid:
            socketio.emit(
                "system_message",
                {"msg": f"⚠️ Você recebeu um aviso de {username}: {reason}", "type": "warning"},
                to=t_sid,
            )

    # ---- /mute ----
    elif cmd == "/mute":
        if not is_privileged:
            return err("Você não tem permissão para usar /mute.")
        if not args:
            return err("Uso: /mute <usuário> [minutos] [razão]")
        target = args[0]
        try:
            minutes = min(int(args[1]), 1440) if len(args) > 1 else 5
        except ValueError:
            minutes = 5
        reason = " ".join(args[2:]) if len(args) > 2 else "Violação das regras"
        muted_users[target] = {
            "until": time.time() + minutes * 60,
            "reason": reason,
            "by": username,
        }
        sys(f"🔇 {target} foi mutado por {minutes} min por {username}. Razão: {reason}")
        t_sid = find_sid(target, room)
        if t_sid:
            socketio.emit(
                "system_message",
                {"msg": f"🔇 Você foi mutado por {minutes} min. Razão: {reason}", "type": "warning"},
                to=t_sid,
            )

    # ---- /unmute ----
    elif cmd == "/unmute":
        if not is_privileged:
            return err("Você não tem permissão para usar /unmute.")
        if not args:
            return err("Uso: /unmute <usuário>")
        target = args[0]
        if target in muted_users:
            del muted_users[target]
            sys(f"🎤 {target} foi desmutado por {username}.")
        else:
            err(f"{target} não está mutado.")

    # ---- /ban ----
    elif cmd == "/ban":
        if not is_privileged:
            return err("Você não tem permissão para usar /ban.")
        if not args:
            return err("Uso: /ban <usuário> [dias] [razão]")
        target = args[0]
        try:
            days = int(args[1]) if len(args) > 1 else 0
        except ValueError:
            days = 0
        reason = " ".join(args[2:]) if len(args) > 2 else "Banimento por administrador"
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=days)
            if days > 0
            else None
        )

        # Buscar IP do usuário alvo
        target_sid = find_sid_global(target)
        target_ip = online_users[target_sid].get("ip") if target_sid else None

        ban = Ban(
            username=target,
            ip_address=target_ip,
            reason=reason,
            banned_by=username,
            expires_at=expires_at,
        )
        db.session.add(ban)
        db.session.commit()

        duration_str = f"por {days} dias" if days > 0 else "permanentemente"
        sys(f"🔨 {target} foi banido {duration_str} por {username}. Razão: {reason}")

        if target_sid:
            socketio.emit(
                "force_kick",
                {"reason": f"Banido {duration_str}: {reason}"},
                to=target_sid,
            )

    # ---- /clear ----
    elif cmd == "/clear":
        if not is_privileged:
            return err("Você não tem permissão para usar /clear.")
        try:
            Message.query.filter_by(room_name=room, deleted=False).update(
                {"deleted": True, "deleted_by": username}
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return err(f"Erro ao limpar mensagens: {exc}")
        sys(f"🗑️ {username} limpou o histórico de mensagens.")
        socketio.emit("clear_chat", {}, to=room)

    # ---- /roomdesc ----
    elif cmd == "/roomdesc":
        if not is_privileged:
            return err("Você não tem permissão para alterar a descrição da sala.")
        if not args:
            return err("Uso: /roomdesc <texto>")
        desc = " ".join(args)[:256]
        if room_obj:
            room_obj.description = desc
            db.session.commit()
        sys(f"📝 Descrição da sala atualizada por {username}.")
        socketio.emit("room_desc_updated", {"description": desc}, to=room)

    # ---- /broadcast ----
    elif cmd == "/broadcast":
        if not is_admin:
            return err("Apenas administradores podem usar /broadcast.")
        if not args:
            return err("Uso: /broadcast <mensagem>")
        sys(f"📢 BROADCAST de {username}: {' '.join(args)}")

    # ---- /pm / /whisper ----
    elif cmd in ("/pm", "/whisper"):
        if len(args) < 2:
            return err("Uso: /pm <usuário> <mensagem>")
        target, pm_text = args[0], replace_emojis(" ".join(args[1:]))
        if not private_chat_enabled.get(target, True):
            return err(f"{target} desativou mensagens privadas.")
        t_sid = find_sid_global(target)
        if not t_sid:
            return err("Usuário não encontrado ou offline.")

        payload = {"from": username, "message": pm_text, "time": now_str(), "role": role}
        socketio.emit("private_message", payload, to=t_sid)
        socketio.emit("private_message", {**payload, "from": f"Para {target}"}, to=sid)

        # Salvar histórico
        from state import pm_history, PM_HISTORY_LIMIT
        key = ":".join(sorted([username, target]))
        pm_history[key].append({"from": username, "message": pm_text, "time": now_str()})
        if len(pm_history[key]) > PM_HISTORY_LIMIT:
            pm_history[key] = pm_history[key][-PM_HISTORY_LIMIT:]

    # ---- /togglepm ----
    elif cmd == "/togglepm":
        current_state = private_chat_enabled.get(username, True)
        private_chat_enabled[username] = not current_state
        status = "ativadas" if not current_state else "desativadas"
        socketio.emit("system_message", {"msg": f"📢 Mensagens privadas {status}.", "type": "info"}, to=sid)

    # ---- /votekick ----
    elif cmd == "/votekick":
        if not args:
            return err("Uso: /votekick <usuário>")
        target = args[0]
        if room in room_votes:
            return err("Já há uma votação em andamento.")
        if not user_in_room(target, room):
            return err(f"{target} não está na sala.")
        room_votes[room] = {
            "type": "kick", "target": target,
            "yes": {sid}, "no": set(),
            "started_by": username, "start_time": time.time(),
        }
        sys(f"📊 Votação iniciada por {username} para expulsar {target}. Vote com /sim ou /não (60s)")
        socketio.start_background_task(vote_timer, room)
        socketio.emit(
            "vote_update",
            {"type": "start", "target": target, "action": "kick", "minutes": None},
            to=room,
        )

    # ---- /votemute ----
    elif cmd == "/votemute":
        if not args:
            return err("Uso: /votemute <usuário> [minutos]")
        target = args[0]
        try:
            minutes = int(args[1]) if len(args) > 1 else 10
        except ValueError:
            minutes = 10
        if room in room_votes:
            return err("Já há uma votação em andamento.")
        if not user_in_room(target, room):
            return err(f"{target} não está na sala.")
        room_votes[room] = {
            "type": "mute", "target": target, "minutes": minutes,
            "yes": {sid}, "no": set(),
            "started_by": username, "start_time": time.time(),
        }
        sys(f"📊 Votação para mutar {target} por {minutes} min. Vote com /sim ou /não (60s)")
        socketio.start_background_task(vote_timer, room)
        socketio.emit(
            "vote_update",
            {"type": "start", "target": target, "action": "mute", "minutes": minutes},
            to=room,
        )

    # ---- /sim /não /yes /no ----
    elif cmd in ("/sim", "/não", "/yes", "/no"):
        if room not in room_votes:
            return err("Não há votação em andamento.")
        vote = room_votes[room]
        if sid in vote["yes"] or sid in vote["no"]:
            return err("Você já votou.")
        if cmd in ("/sim", "/yes"):
            vote["yes"].add(sid)
            socketio.emit("system_message", {"msg": "✅ Voto SIM registrado.", "type": "info"}, to=sid)
        else:
            vote["no"].add(sid)
            socketio.emit("system_message", {"msg": "❌ Voto NÃO registrado.", "type": "info"}, to=sid)
        sys(f"📊 Votação: 👍 {len(vote['yes'])} | 👎 {len(vote['no'])}")

    # ---- /emojis ----
    elif cmd == "/emojis":
        from utils import EMOJI_MAP
        lines = "\n".join(f"{k} → {v}" for k, v in list(EMOJI_MAP.items())[:20])
        socketio.emit(
            "system_message",
            {"msg": f"📝 Emojis disponíveis:\n{lines}\nUse :código: nas mensagens.", "type": "info"},
            to=sid,
        )

    # ---- /help ----
    elif cmd == "/help":
        socketio.emit("system_message", {"msg": HELP_TEXT, "type": "info"}, to=sid)

    else:
        err(f"Comando não reconhecido: {cmd}. Digite /help para ajuda.")