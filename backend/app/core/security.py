"""
JWT-based auth, backed by PostgreSQL as of KNOT6 Phase 1.

`create_access_token()` / `decode_token()` are unchanged from pre-Phase-1:
still a stateless JWT carrying `sub`/`role`/`name`, so every route's
`get_current_user()` dependency (`api/deps.py`) needed zero changes and
there is no DB round-trip on every authenticated request.

What changed: `authenticate()` now checks a `User` row in PostgreSQL
(`app/db/models.py`) instead of a hardcoded dict, so accounts survive a
backend restart. `ensure_demo_users()` seeds the same three demo accounts
the README has always documented (plus a fourth, `viewer`, now that the PS
spec's four-role vocabulary -- Admin/Investigator/Analyst/Viewer -- is
supported) idempotently on startup, with the *same* credentials as before,
so nothing about the demo login experience changed.

Roles are kept as the lowercase strings already used throughout
`app/api/routes/*.py`'s `require_role("investigator", "analyst", "admin")`
calls -- deliberately, to preserve every existing authorization call site
byte-for-byte rather than a mechanical uppercase rename across five files.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLES = ("admin", "investigator", "analyst", "viewer")

# Same three demo accounts the README has documented since before Phase 1,
# plus `viewer` for the PS's fourth role. Seeded idempotently into
# PostgreSQL on startup (see `ensure_demo_users`) -- credentials unchanged.
_DEMO_ACCOUNTS = {
    "admin": {"password": "admin123", "role": "admin", "full_name": "SP Admin"},
    "investigator": {
        "password": "investigator123", "role": "investigator",
        "full_name": "Inspector R. Sharma",
    },
    "analyst": {
        "password": "analyst123", "role": "analyst", "full_name": "Intel Analyst K. Verma",
    },
    "viewer": {"password": "viewer123", "role": "viewer", "full_name": "Read-Only Viewer"},
}


class AuthUser(BaseModel):
    username: str
    role: str  # "investigator" | "admin" | "analyst" | "viewer"
    full_name: str


def ensure_demo_users(db: Session) -> None:
    """Idempotent: safe to call on every startup. Only inserts accounts that don't exist yet."""
    for username, record in _DEMO_ACCOUNTS.items():
        if db.query(User).filter(User.username == username).first():
            continue
        db.add(User(
            username=username,
            hashed_password=pwd_context.hash(record["password"]),
            role=record["role"],
            full_name=record["full_name"],
        ))
    db.commit()


def authenticate(username: str, password: str, db: Session) -> Optional[AuthUser]:
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        return None
    return AuthUser(username=user.username, role=user.role, full_name=user.full_name)


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
