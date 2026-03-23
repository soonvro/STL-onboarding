from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt


class AdminAuthError(RuntimeError):
    """Raised when admin authentication fails."""


@dataclass(slots=True)
class AdminAuthService:
    secret: str
    ttl_minutes: int
    issuer: str = "qna-backend"

    def verify_password(self, actual_password: str, expected_password: str) -> bool:
        return hmac.compare_digest(actual_password, expected_password)

    def issue_token(self) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": "admin",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self.ttl_minutes)).timestamp()),
            "iss": self.issuer,
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def decode_token(self, token: str) -> dict[str, object]:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"], issuer=self.issuer)
        except jwt.PyJWTError as exc:
            raise AdminAuthError("invalid admin session") from exc
        if payload.get("sub") != "admin":
            raise AdminAuthError("invalid admin session")
        return payload
