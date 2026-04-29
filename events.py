"""
events.py — Handlers de eventos SocketIO do Nexus Chat.
"""

from __future__ import annotations

import base64
import os
import time
import uuid
from datetime import timezone, datetime

from flask import current_app, request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from antispam import check_mute, check_spam, check_ip_rate, cleanup_spam_data, is_banned
from commands import handle_command
from extensions import db, socketio
from models import Message, Room, User
from state import (
    guest_warnings_sent,
    online_users,
    private_chat_enabled,
    room_admins,
    room_users,
    room_votes,
    typing_users,
    visitors,
    user_sessions,
)
from utils import (
    build_message_payload,
    file_type_from_ext,
    get_rooms_list,
    now_str,
    replace_emojis,
    system_msg,
    touch_room,
    update_room_users,
)


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------

@socketio.on("connect")
def handle_connect():
    current_app.logger.info("[NEXUS] Connect: %s", request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    user_info = online_users.get(sid)

    visitors.pop(sid, None)
    guest_warnings_sent.discard(sid)

    if not user_info:
        return

    username = user_info["username"]
    room = user_info.get("room")

    if user_sessions.get(username) == sid:
        user_sessions.pop(username, None)

    if room:
        typing_users[room].discard(username)
        room_users[room] = [u for u in room_users[room] if u != username]
        system_msg(room, f"🔴 {username} desconectou.")
        update_room_users(room)
        leave_room(room)

    cleanup_spam_data(username)
    online_users.pop(sid, None)


@socketio.on("logout")
def handle_logout():
    sid = request.sid
    user_info = online_users.get(sid)
    if user_info:
        username = user_info["username"]
        room = user_info.get("room")
        if room:
            typing_users[room].discard(username)
            room_users[room] = [u for u in room_users[room] if u != username]
            system_msg(room, f"🔴 {username} saiu.")
            update_room_users(room)
            leave_room(room)
        online_users.pop(sid, None)
        user_sessions.pop(username, None)
        visitors.pop(sid, None)
    emit("left_room", {})


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

@socketio.on("join_guest")
def on_guest_join(data: dict):
    sid = request.sid
    ip = request.remote_addr or "0.0.0.0"

    # Verificar ban por IP
    banned, reason = is_banned(None, ip)
    if banned:
        emit("force_kick", {"reason": f"Acesso negado: {reason}"})
        return

    username = f"Guest_{sid[-6:].upper()}"

    old_sid = user_sessions.get(username)
    if old_sid and old_sid in online_users:
        online_users.pop(old_sid, None)
        visitors.pop(old_sid, None)

    visitors[sid] = time.time()
    user_sessions[username] = sid
    online_users[sid] = {
        "username": username,
        "room": None,
        "role": "guest",
        "join_time": time.time(),
        "user_id": None,
        "ip": ip,
    }
    private_chat_enabled[username] = True

    emit("login_success", {"username": username, "role": "guest", "avatar": "👤"})
    emit("room_list", get_rooms_list())


@socketio.on("join_auth")
def on_auth_join(data: dict):
    sid = request.sid
    ip = request.remote_addr or "0.0.0.0"
    username = (
        current_user.username
        if current_user.is_authenticated
        else data.get("username", "").strip()
    )

    if not username:
        emit("error", {"msg": "Nome de usuário não fornecido."})
        return

    # Verificar ban
    banned, reason = is_banned(username, ip)
    if banned:
        emit("force_kick", {"reason": f"Acesso negado: {reason}"})
        return

    old_sid = user_sessions.get(username)
    if old_sid and old_sid in online_users:
        old_room = online_users[old_sid].get("room")
        if old_room:
            system_msg(old_room, f"🔄 {username} reconectou de outro dispositivo.")
            room_users[old_room] = [u for u in room_users[old_room] if u != username]
            typing_users[old_room].discard(username)
            update_room_users(old_room)
        online_users.pop(old_sid, None)

    user_db = User.query.filter_by(username=username).first()
    role = "admin" if (user_db and user_db.is_admin) else "user"

    user_sessions[username] = sid
    online_users[sid] = {
        "username": username,
        "room": None,
        "role": role,
        "join_time": time.time(),
        "user_id": user_db.id if user_db else None,
        "ip": ip,
    }
    private_chat_enabled[username] = True

    emit("login_success", {
        "username": username,
        "role": role,
        "is_admin": user_db.is_admin if user_db else False,
        "avatar": user_db.avatar or "👤" if user_db else "👤",
    })
    emit("room_list", get_rooms_list())


# ---------------------------------------------------------------------------
# Salas
# ---------------------------------------------------------------------------

@socketio.on("create_room")
def on_create_room(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    room_name = data.get("name", "").strip()

    if not room_name:
        return emit("create_room_result", {"success": False, "msg": "Nome da sala é obrigatório."})
    if len(room_name) > 64:
        return emit("create_room_result", {"success": False, "msg": "Nome muito longo (máx. 64 caracteres)."})
    if Room.query.filter_by(name=room_name).first():
        return emit("create_room_result", {"success": False, "msg": "Já existe uma sala com esse nome."})

    try:
        owner_id = user_info.get("user_id") if user_info else None
        owner_name = user_info["username"] if user_info else "Guest"

        room = Room(
            name=room_name,
            owner_id=owner_id,
            created_by=owner_name,
            description=data.get("description", ""),
            last_activity=datetime.now(timezone.utc),
        )
        if data.get("password"):
            room.set_password(data["password"])

        db.session.add(room)
        db.session.commit()

        if owner_id:
            room_admins[room_name].append(owner_name)

        socketio.emit("room_list", get_rooms_list())
        emit("create_room_result", {"success": True, "msg": f'Sala "{room_name}" criada!'})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("Erro ao criar sala: %s", exc)
        emit("create_room_result", {"success": False, "msg": "Erro interno ao criar a sala."})


@socketio.on("join_room")
def on_join_room(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info:
        return emit("error", {"msg": "Sessão não encontrada. Recarregue a página."})

    room_obj = Room.query.filter_by(name=data.get("name", "")).first()
    if not room_obj:
        return emit("error", {"msg": "Sala não encontrada."})

    if room_obj.is_private and not room_obj.check_password(data.get("password", "")):
        return emit("error", {"msg": "Senha incorreta."})

    # Verificar lotação
    current_in_room = sum(1 for u in online_users.values() if u.get("room") == room_obj.name)
    if current_in_room >= room_obj.max_users:
        return emit("error", {"msg": f"Sala cheia ({room_obj.max_users} usuários)."})

    username = user_info["username"]

    # Sair da sala anterior
    old_room = user_info.get("room")
    if old_room:
        leave_room(old_room)
        typing_users[old_room].discard(username)
        room_users[old_room] = [u for u in room_users[old_room] if u != username]
        if room_users[old_room]:
            system_msg(old_room, f"🚪 {username} saiu.")
            update_room_users(old_room)

    join_room(room_obj.name)
    user_info["room"] = room_obj.name

    if username not in room_users[room_obj.name]:
        room_users[room_obj.name].append(username)

    touch_room(room_obj.name)

    is_room_admin = username in room_admins[room_obj.name] or user_info["role"] == "admin"
    is_owner = room_obj.owner_id is not None and room_obj.owner_id == user_info.get("user_id")

    emit("joined_room", {
        "name": room_obj.name,
        "description": room_obj.description or "",
        "owner_id": room_obj.owner_id,
        "is_owner": is_owner,
        "is_admin": is_room_admin,
        "created_by": room_obj.created_by,
    })

    # Histórico — emite como array (room_history) E individualmente (message)
    messages = (
        Message.query
        .filter_by(room_name=room_obj.name, deleted=False)
        .order_by(Message.timestamp.desc())
        .limit(100)
        .all()
    )
    history_payload = []
    for msg in reversed(messages):
        payload = build_message_payload(msg, user_info, room_obj.name)
        emit("message", payload, to=sid)
        history_payload.append(payload)

    emit("room_history", history_payload, to=sid)

    system_msg(room_obj.name, f"🟢 {username} entrou na sala.")
    update_room_users(room_obj.name)

    # Descrição da sala
    if room_obj.description:
        socketio.emit(
            "system_message",
            {"msg": f"📝 {room_obj.description}", "type": "info"},
            to=sid,
        )


@socketio.on("leave_room")
def on_leave_room(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return

    room = user_info["room"]
    username = user_info["username"]

    leave_room(room)
    typing_users[room].discard(username)
    room_users[room] = [u for u in room_users[room] if u != username]
    system_msg(room, f"🚪 {username} saiu.")
    update_room_users(room)
    user_info["room"] = None

    emit("left_room", {})


# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------

@socketio.on("send_message")
def on_message(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return

    room = user_info["room"]
    username = user_info["username"]
    ip = user_info.get("ip", "0.0.0.0")
    raw_msg = data.get("message", "").strip()
    reply_to = data.get("reply_to")

    if not raw_msg:
        return

    # Rate limit por IP
    if not check_ip_rate(ip):
        emit("error", {"msg": "Muitas mensagens. Aguarde um momento."})
        return

    # Anti-spam por usuário
    ok, spam_reason = check_spam(username, room)
    if not ok:
        emit("error", {"msg": spam_reason or "Aguarde antes de enviar outra mensagem."})
        return

    # Verificar mute
    is_muted, remaining = check_mute(username, room)
    if is_muted:
        reason = muted_users[username].get("reason", "N/A") if username in muted_users else "N/A"
        emit("error", {"msg": f"Você está mutado por {remaining}s. Motivo: {reason}"})
        return

    msg = replace_emojis(raw_msg)

    # Parar typing indicator ao enviar
    typing_users[room].discard(username)
    socketio.emit("typing_update", {"users": list(typing_users[room])}, to=room)

    # Processar comandos
    if msg.startswith("/"):
        handle_command(sid, room, msg)
        return

    touch_room(room)

    # Persistir
    message_id = None
    if user_info.get("user_id"):
        room_obj = Room.query.filter_by(name=room).first()
        try:
            reply_id = reply_to.get("id") if isinstance(reply_to, dict) else reply_to
            message = Message(
                room_id=room_obj.id if room_obj else None,
                room_name=room,
                username=username,
                content=msg,
                content_type="text",
                reply_to=reply_id,
                user_id=user_info["user_id"],
            )
            db.session.add(message)
            db.session.commit()
            message_id = message.id
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Erro ao salvar mensagem: %s", exc)

    is_room_admin = username in room_admins[room] or user_info["role"] == "admin"

    socketio.emit("message", {
        "id": message_id,
        "user": username,
        "text": msg,
        "type": "text",
        "time": now_str(),
        "role": "admin" if is_room_admin else user_info["role"],
        "reply_to": reply_to,
        "can_delete": message_id is not None,
    }, to=room)


@socketio.on("delete_message")
def on_delete_message(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return

    room = user_info["room"]
    username = user_info["username"]
    message_id = data.get("message_id")

    if not message_id:
        return emit("error", {"msg": "ID da mensagem não fornecido."})

    message = db.session.get(Message, message_id)
    if not message:
        return emit("error", {"msg": "Mensagem não encontrada."})

    is_room_admin = username in room_admins[room] or user_info["role"] == "admin"
    is_owner_msg = message.user_id == user_info.get("user_id")

    if not (is_room_admin or is_owner_msg):
        return emit("error", {"msg": "Você não tem permissão para deletar esta mensagem."})

    try:
        message.deleted = True
        message.deleted_by = username
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("Erro ao deletar mensagem: %s", exc)
        return emit("error", {"msg": "Erro ao deletar mensagem."})

    socketio.emit("message_deleted", {"message_id": message_id, "deleted_by": username}, to=room)


# ---------------------------------------------------------------------------
# Upload de arquivos
# ---------------------------------------------------------------------------

@socketio.on("upload_file")
def on_upload(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return emit("error", {"msg": "Você não está em uma sala."})

    username = user_info["username"]
    room = user_info["room"]

    ok, reason = check_spam(username, room, is_file=True)
    if not ok:
        return emit("error", {"msg": reason or "Aguarde antes de enviar outro arquivo."})

    original_name = data.get("name", "upload")
    safe_name = f"{uuid.uuid4().hex[:8]}_{original_name}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    filepath = os.path.join(upload_folder, safe_name)

    try:
        raw = data.get("data", "")
        if isinstance(raw, str) and raw.startswith("data:"):
            _, encoded = raw.split(",", 1)
            file_bytes = base64.b64decode(encoded)
        elif isinstance(raw, (bytes, bytearray)):
            file_bytes = bytes(raw)
        else:
            return emit("error", {"msg": "Formato de arquivo inválido."})

        with open(filepath, "wb") as fh:
            fh.write(file_bytes)

        url = f"/uploads/{safe_name}"
        file_type = file_type_from_ext(original_name)
        touch_room(room)

        message_id = None
        if user_info.get("user_id"):
            room_obj = Room.query.filter_by(name=room).first()
            try:
                msg_obj = Message(
                    room_id=room_obj.id if room_obj else None,
                    room_name=room,
                    username=username,
                    content=original_name,
                    content_type=file_type,
                    file_url=url,
                    user_id=user_info["user_id"],
                )
                db.session.add(msg_obj)
                db.session.commit()
                message_id = msg_obj.id
            except Exception as exc:
                db.session.rollback()
                current_app.logger.error("Erro ao salvar upload no DB: %s", exc)

        is_room_admin = username in room_admins[room] or user_info["role"] == "admin"

        socketio.emit("message", {
            "id": message_id,
            "user": username,
            "text": original_name,
            "url": url,
            "type": file_type,
            "time": now_str(),
            "role": "admin" if is_room_admin else user_info["role"],
            "can_delete": message_id is not None,
        }, to=room)

    except Exception as exc:
        current_app.logger.error("Erro ao processar upload: %s", exc)
        emit("error", {"msg": "Erro ao enviar arquivo."})


# ---------------------------------------------------------------------------
# Votação (via socket, além de /votekick e /votemute)
# ---------------------------------------------------------------------------

@socketio.on("vote_action")
def on_vote_action(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return

    room = user_info["room"]
    action = data.get("action")

    if room not in room_votes:
        return emit("error", {"msg": "Não há votação ativa no momento."})

    vote = room_votes[room]
    if sid in vote["yes"] or sid in vote["no"]:
        return emit("error", {"msg": "Você já votou nesta votação."})

    if action == "yes":
        vote["yes"].add(sid)
        emit("system_message", {"msg": "✅ Voto SIM registrado.", "type": "info"})
    elif action == "no":
        vote["no"].add(sid)
        emit("system_message", {"msg": "❌ Voto NÃO registrado.", "type": "info"})
    else:
        return emit("error", {"msg": "Ação de voto inválida."})

    system_msg(room, f"📊 Votação: 👍 {len(vote['yes'])} | 👎 {len(vote['no'])}")


# ---------------------------------------------------------------------------
# Typing indicator
# ---------------------------------------------------------------------------

@socketio.on("typing_start")
def on_typing_start(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return
    room = user_info["room"]
    username = user_info["username"]
    typing_users[room].add(username)
    socketio.emit("typing_update", {"users": list(typing_users[room])}, to=room)


@socketio.on("typing_stop")
def on_typing_stop(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info or not user_info.get("room"):
        return
    room = user_info["room"]
    username = user_info["username"]
    typing_users[room].discard(username)
    socketio.emit("typing_update", {"users": list(typing_users[room])}, to=room)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@socketio.on("toggle_private_messages")
def on_toggle_pm(data: dict):
    sid = request.sid
    user_info = online_users.get(sid)
    if not user_info:
        return
    username = user_info["username"]
    current_state = private_chat_enabled.get(username, True)
    private_chat_enabled[username] = not current_state
    status = "ativadas" if not current_state else "desativadas"
    emit("system_message", {"msg": f"📢 Mensagens privadas {status}.", "type": "info"})


@socketio.on("get_user_list")
def on_get_user_list():
    sid = request.sid
    user_info = online_users.get(sid)
    if user_info and user_info.get("room"):
        room = user_info["room"]
        emit("user_list", {"users": room_users[room], "count": len(room_users[room])})


@socketio.on("get_room_list")
def on_get_room_list():
    emit("room_list", get_rooms_list())


# Importação circular necessária para acessar muted_users no on_message
from state import muted_users  # noqa: E402