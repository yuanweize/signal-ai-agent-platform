"""In-memory authentication rate limiting and lockout guards."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.config import settings


class LoginGuard:
    def __init__(self) -> None:
        self._ip_attempts: dict[str, deque[float]] = defaultdict(deque)
        self._user_attempts: dict[str, deque[float]] = defaultdict(deque)
        self._locked_ip_until: dict[str, float] = {}
        self._locked_user_until: dict[str, float] = {}

    def _trim(self, attempts: deque[float], now: float) -> None:
        window_start = now - settings.login_rate_limit_window_seconds
        while attempts and attempts[0] < window_start:
            attempts.popleft()

    def check_allowed(self, ip: str, username: str) -> tuple[bool, int]:
        now = time.time()
        ip_locked_until = self._locked_ip_until.get(ip, 0)
        user_locked_until = self._locked_user_until.get(username, 0)
        locked_until = max(ip_locked_until, user_locked_until)
        if locked_until > now:
            return False, int(locked_until - now)
        return True, 0

    def on_failed_attempt(self, ip: str, username: str) -> None:
        now = time.time()

        ip_attempts = self._ip_attempts[ip]
        user_attempts = self._user_attempts[username]

        self._trim(ip_attempts, now)
        self._trim(user_attempts, now)

        ip_attempts.append(now)
        user_attempts.append(now)

        if len(ip_attempts) >= settings.login_rate_limit_max_attempts_per_ip:
            self._locked_ip_until[ip] = now + settings.login_lock_seconds
            ip_attempts.clear()

        if len(user_attempts) >= settings.login_rate_limit_max_attempts_per_user:
            self._locked_user_until[username] = now + settings.login_lock_seconds
            user_attempts.clear()

    def on_success(self, ip: str, username: str) -> None:
        self._ip_attempts.pop(ip, None)
        self._user_attempts.pop(username, None)
        self._locked_ip_until.pop(ip, None)
        self._locked_user_until.pop(username, None)


login_guard = LoginGuard()
