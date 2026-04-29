"""
state.py — Estado em memória compartilhado entre os módulos.
Todo acesso a estas estruturas deve ser thread-safe quando necessário.
"""

from collections import defaultdict
from threading import Lock
from typing import Any

# sid → { username, room, role, join_time, user_id, ip }
online_users: dict[str, dict[str, Any]] = {}

# username → sid (última sessão)
user_sessions: dict[str, str] = {}

# room_name → [usernames]
room_users: dict[str, list[str]] = defaultdict(list)

# room_name → [admin usernames]
room_admins: dict[str, list[str]] = defaultdict(list)

# room_name → vote dict
room_votes: dict[str, dict[str, Any]] = {}
room_locks: dict[str, Lock] = defaultdict(Lock)

# sid → join timestamp (guests)
visitors: dict[str, float] = {}
guest_warnings_sent: set[str] = set()

# username → { until, reason, by }
muted_users: dict[str, dict[str, Any]] = {}

# username → [{ reason, by, time }]
warning_log: dict[str, list[dict]] = defaultdict(list)

# username:room → { time, count, file_time, file_count }
user_last_message: dict[str, dict[str, Any]] = {}

# ip → { time, count }  — rate limit global por IP
ip_message_counts: dict[str, dict[str, Any]] = {}

# username → bool
private_chat_enabled: dict[str, bool] = {}

# room_name → set de usernames digitando
typing_users: dict[str, set[str]] = defaultdict(set)

# "user_a:user_b" (ordenado) → list de msgs (últimas 100)
pm_history: dict[str, list[dict]] = defaultdict(list)

PM_HISTORY_LIMIT = 100
