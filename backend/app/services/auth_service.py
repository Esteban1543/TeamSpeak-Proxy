"""Autenticación del único administrador y tokens de sesión firmados."""

from __future__ import annotations

import asyncio
import hmac
import time

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Hash fijo para gastar el mismo tiempo cuando el usuario no coincide.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(rounds=12))


class LoginThrottle:
    """Bloquea temporalmente una IP tras demasiados intentos fallidos."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 900) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = time.monotonic()
        attempts = [t for t in self._failures.get(key, []) if now - t < self.window]
        if attempts:
            self._failures[key] = attempts
        else:
            self._failures.pop(key, None)
        return attempts

    def retry_after(self, key: str) -> int:
        attempts = self._recent(key)
        if len(attempts) < self.max_attempts:
            return 0
        return max(1, int(self.window - (time.monotonic() - attempts[0])))

    def failure(self, key: str) -> None:
        self._failures.setdefault(key, []).append(time.monotonic())

    def success(self, key: str) -> None:
        self._failures.pop(key, None)


class AuthService:
    def __init__(self, admin_user: str, password_hash: str, secret: str, expire_hours: int) -> None:
        self._user = admin_user
        self._hash = password_hash.encode()
        # El hash forma parte de la sal: cambiar la contraseña invalida las sesiones abiertas.
        self._serializer = URLSafeTimedSerializer(secret, salt=f"ts3-proxy-session:{password_hash}")
        self.max_age = expire_hours * 3600
        self.throttle = LoginThrottle()

    async def verify(self, username: str, password: str) -> bool:
        user_ok = hmac.compare_digest(username.encode(), self._user.encode())
        pw = password.encode()[:72]
        hashed = self._hash if user_ok else _DUMMY_HASH
        try:
            pw_ok = await asyncio.to_thread(bcrypt.checkpw, pw, hashed)
        except ValueError:
            return False
        return user_ok and pw_ok

    def issue_token(self) -> str:
        return self._serializer.dumps({"u": self._user})

    def validate_token(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=self.max_age)
        except (BadSignature, SignatureExpired):
            return None
        user = data.get("u") if isinstance(data, dict) else None
        return user if user == self._user else None
