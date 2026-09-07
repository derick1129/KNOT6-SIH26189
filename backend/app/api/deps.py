"""Shared FastAPI dependencies: auth extraction + role gating + the graph-store singleton."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import AuthUser, decode_token
from app.db.graph_store import GraphStore, get_graph_store

_bearer = HTTPBearer(auto_error=False)


def get_store() -> GraphStore:
    return get_graph_store()


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> AuthUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")
    user = decode_token(creds.credentials)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    return user


def require_role(*roles: str):
    def _check(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                 f"Role '{user.role}' is not permitted to perform this action.")
        return user
    return _check
