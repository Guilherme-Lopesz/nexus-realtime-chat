"""
app.py — Ponto de entrada do Nexus Chat.
Cria a aplicação Flask, registra extensões, blueprints e inicia tasks.
"""

from __future__ import annotations

import logging
import os
from threading import Thread

from flask import Flask
from flask_login import LoginManager

from extensions import bcrypt, db, login_manager, socketio
from models import User


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ── Configuração ──────────────────────────────────────────────────────
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "nexus-dev-secret-CHANGE-IN-PROD"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///nexus.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), "uploads"),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB
    )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Extensões ─────────────────────────────────────────────────────────
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return db.session.get(User, int(user_id))

    # ── Blueprints ────────────────────────────────────────────────────────
    from routes import bp as routes_bp
    # Sobrescrever pasta de uploads para o blueprint
    routes_bp.static_folder = app.config["UPLOAD_FOLDER"]
    app.register_blueprint(routes_bp)

    # ── Eventos SocketIO (registra handlers via import) ───────────────────
    import events  # noqa: F401

    return app


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    app = create_app()

    with app.app_context():
        db.create_all()
        from models import Room

        rooms = Room.query.count()
        users = User.query.count()
        app.logger.info(
            "[NEXUS] Banco inicializado — %d salas, %d usuários", rooms, users
        )

    # Background tasks
    from tasks import check_guest_time, cleanup_inactive_rooms, cleanup_typing

    Thread(target=check_guest_time, daemon=True).start()
    Thread(target=cleanup_inactive_rooms, daemon=True).start()
    Thread(target=cleanup_typing, daemon=True).start()

    app.logger.info("[NEXUS] Servidor iniciando em 0.0.0.0:8080")

    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        allow_unsafe_werkzeug=True,
        debug=os.environ.get("DEBUG", "true").lower() == "true",
    )