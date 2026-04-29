"""
routes.py — Rotas HTTP do Nexus Chat.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from extensions import db
from models import User
from state import online_users

bp = Blueprint("routes", __name__)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@bp.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Arquivos enviados pelos usuários
# ---------------------------------------------------------------------------

@bp.route("/uploads/<path:filename>")
def serve_upload(filename):
    upload_folder = bp.static_folder or os.path.join(os.path.dirname(__file__), "uploads")
    return send_from_directory(upload_folder, filename)


# ---------------------------------------------------------------------------
# API de autenticação
# ---------------------------------------------------------------------------

@bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "msg": "Usuário e senha são obrigatórios."}), 400

    if len(username) < 3 or len(username) > 32:
        return jsonify({"success": False, "msg": "Usuário deve ter entre 3 e 32 caracteres."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "msg": "A senha deve ter no mínimo 6 caracteres."}), 400

    # Permitir apenas alfanuméricos e _
    import re
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return jsonify({"success": False, "msg": "Usuário inválido (use apenas letras, números e _)."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "msg": "Nome de usuário já está em uso."}), 409

    user = User(username=username)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "success": True,
        "msg": "Conta criada com sucesso!",
        "username": user.username,
        "is_admin": user.is_admin,
        "role": user.role,
        "avatar": user.avatar or "👤",
    })


@bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "msg": "Usuário e senha são obrigatórios."}), 400

    # Verificar ban
    from antispam import is_banned
    ip = request.remote_addr
    banned, ban_reason = is_banned(username, ip)
    if banned:
        return jsonify({"success": False, "msg": f"Acesso negado. {ban_reason}"}), 403

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"success": False, "msg": "Usuário ou senha incorretos."}), 401

    return jsonify({
        "success": True,
        "msg": "Login realizado com sucesso!",
        "username": user.username,
        "is_admin": user.is_admin,
        "role": user.role,
        "avatar": user.avatar or "👤",
    })


# ---------------------------------------------------------------------------
# API de stats / perfil
# ---------------------------------------------------------------------------

@bp.route("/api/user_stats")
def api_user_stats():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"success": False, "msg": "Parâmetro username obrigatório."}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"success": False, "msg": "Usuário não encontrado."}), 404

    is_online = any(u["username"] == username for u in online_users.values())

    return jsonify({
        "success": True,
        "username": user.username,
        "is_admin": user.is_admin,
        "warnings": user.warnings,
        "avatar": user.avatar or "👤",
        "bio": user.bio or "",
        "created_at": user.created_at.isoformat(),
        "is_online": is_online,
        "message_count": len(user.messages),
    })


@bp.route("/api/pm_history")
def api_pm_history():
    """Retorna histórico de mensagens privadas entre dois usuários."""
    me = request.args.get("me", "").strip()
    other = request.args.get("other", "").strip()
    if not me or not other:
        return jsonify({"success": False, "msg": "Parâmetros 'me' e 'other' obrigatórios."}), 400

    from state import pm_history
    key = ":".join(sorted([me, other]))
    history = pm_history.get(key, [])
    return jsonify({"success": True, "history": history})