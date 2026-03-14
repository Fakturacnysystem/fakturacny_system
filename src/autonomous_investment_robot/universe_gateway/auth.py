from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from autonomous_investment_robot.universe_gateway.contracts import UniverseRole


ROLE_RANK: dict[str, int] = {
    "observer": 0,
    "analyst": 1,
    "operator": 2,
    "admin": 3,
}


@dataclass(frozen=True)
class AuthIdentity:
    username: str
    role: UniverseRole


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _jwt_sign(signing_input: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return _b64url(sig)


def hash_password(password: str, *, salt: str | None = None) -> str:
    safe_salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256(f"{safe_salt}:{password}".encode("utf-8")).hexdigest()
    return f"{safe_salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    if "$" not in password_hash:
        return False
    salt, expected = password_hash.split("$", 1)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected)


def issue_token(*, username: str, role: UniverseRole, secret: str, ttl_s: int = 3600) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(username),
        "role": str(role),
        "iat": now,
        "exp": now + max(30, int(ttl_s)),
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _jwt_sign(signing_input, secret)
    return f"{signing_input}.{signature}"


def decode_token(token: str, *, secret: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise ValueError("invalid_token_format")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _jwt_sign(signing_input, secret)
    if not hmac.compare_digest(expected, parts[2]):
        raise ValueError("invalid_token_signature")
    payload_raw = _b64url_decode(parts[1]).decode("utf-8", errors="strict")
    payload = json.loads(payload_raw)
    if not isinstance(payload, dict):
        raise ValueError("invalid_token_payload")
    exp = int(payload.get("exp", 0) or 0)
    if exp <= int(time.time()):
        raise ValueError("token_expired")
    role = str(payload.get("role", "") or "")
    if role not in ROLE_RANK:
        raise ValueError("invalid_token_role")
    return payload


def role_allows(identity_role: UniverseRole, required_roles: set[UniverseRole]) -> bool:
    if not required_roles:
        return True
    identity_rank = ROLE_RANK.get(str(identity_role), -1)
    return any(identity_rank >= ROLE_RANK.get(str(required), 100) for required in required_roles)


class AuthService:
    """Auth service with DB-backed users and JWT token issuance."""

    def __init__(self, *, store: Any, jwt_secret: str) -> None:
        self.store = store
        self.jwt_secret = str(jwt_secret or "").strip() or "unsafe-dev-secret"

    def ensure_default_admin(self) -> None:
        if self.store.count_users() > 0:
            return
        default_password = "universe-admin"
        self.store.upsert_user(
            username="admin",
            role="admin",
            password_hash=hash_password(default_password),
            active=True,
        )

    def authenticate_user(self, username: str, password: str) -> AuthIdentity | None:
        user = self.store.get_user(username)
        if not user:
            return None
        if not bool(user.get("active", True)):
            return None
        if not verify_password(password, str(user.get("password_hash", "") or "")):
            return None
        role = str(user.get("role", "observer") or "observer")
        if role not in ROLE_RANK:
            role = "observer"
        return AuthIdentity(username=str(user.get("username") or username), role=role)  # type: ignore[arg-type]

    def issue_identity_token(self, identity: AuthIdentity, ttl_s: int = 3600) -> str:
        return issue_token(username=identity.username, role=identity.role, secret=self.jwt_secret, ttl_s=ttl_s)

    def parse_identity(self, token: str) -> AuthIdentity:
        payload = decode_token(token, secret=self.jwt_secret)
        username = str(payload.get("sub", "") or "")
        role = str(payload.get("role", "observer") or "observer")
        if role not in ROLE_RANK:
            role = "observer"
        return AuthIdentity(username=username, role=role)  # type: ignore[arg-type]
