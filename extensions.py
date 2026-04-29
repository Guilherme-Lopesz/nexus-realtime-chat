"""
extensions.py — Instâncias compartilhadas das extensões Flask.
Criado aqui para evitar importações circulares.
"""

from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
bcrypt = Bcrypt()
login_manager = LoginManager()
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)
