"""
Minimal JWT-based auth stub.

This is intentionally thin: the PS's real requirement is the analysis
engine, not an identity system. What's implemented is real (issue/verify
JWTs, role claim, password hashing) so the seam is correct; a production
rollout would swap this for the agency's existing SSO / CCTNS identity
provider without touching anything downstream, because every route only
depends on `get_current_user()` -> `AuthUser`.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthUser(BaseModel):
    username: str
    role: str  # "investigator" | "admin" | "analyst"
    full_name: str


# Demo user directory. In production this is a lookup against the
# agency's identity provider / CCTNS account store, not a constant.
_DEMO_USERS = {
    "admin": {"password": "admin123", "role": "admin", "full_name": "SP Admin"},
    "investigator": {
        "password": "investigator123",
        "role": "investigator",
        "full_name": "Inspector R. Sharma",
    },
    "analyst": {
        "password": "analyst123",
        "role": "analyst",
        "full_name": "Intel Analyst K. Verma",
    },
}


def authenticate(username: str, password: str) -> Optional[AuthUser]:
    record = _DEMO_USERS.get(username)
    if not record or record["password"] != password:
        return None
    return AuthUser(username=username, role=record["role"], full_name=record["full_name"])


def create_access_token(user: AuthUser) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {
        "sub": user.username,
        "role": user.role,
        "name": user.full_name,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[AuthUser]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    return AuthUser(username=payload["sub"], role=payload["role"], full_name=payload["name"])
