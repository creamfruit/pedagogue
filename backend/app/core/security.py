from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = settings.jwt_algorithm


class PasswordHasher:
    def __init__(self, rounds: int = 12) -> None:
        self.rounds = rounds

    def hash(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self.rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False


class TokenService:
    def __init__(self, secret: str, algorithm: str = ALGORITHM, expire_minutes: Optional[int] = None) -> None:
        self.secret = secret
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes or settings.access_token_expire_minutes

    def create_access_token(self, subject: str, extra: Optional[dict[str, Any]] = None) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self.expire_minutes)).timestamp()),
            "type": "access",
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode(self, token: str) -> Optional[dict[str, Any]]:
        try:
            return jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except JWTError:
            return None

    def subject(self, token: str) -> Optional[str]:
        payload = self.decode(token)
        if payload is None or payload.get("type") != "access":
            return None
        return payload.get("sub")

    @property
    def expires_in(self) -> int:
        return self.expire_minutes * 60


hasher = PasswordHasher()
tokens = TokenService(settings.secret_key)
