"""Shared FastAPI dependencies: auth extraction + role gating + the graph-store singleton."""
from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import AuthUser, decode_token
from app.db.graph_store import GraphStore, ScopedGraphStore, get_graph_store
from app.db.postgres import get_db as _get_db

_bearer = HTTPBearer(auto_error=False)


def get_store() -> GraphStore:
    return get_graph_store()


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


def get_store_for(investigation_id: str | None = None,
                   store: GraphStore = Depends(get_store)) -> GraphStore:
    """
    KNOT6 Phase 1: the investigation-aware graph-store dependency.

    - Omitted (the default): returns the raw, unscoped store -- byte-for-byte
      today's pre-Phase-1 behavior, so every existing route/test that never
      passes `investigation_id` is unaffected.
    - Provided (as a query param on legacy routes, or a path param of the
      same name on the new `/api/investigations/{investigation_id}/...`
      routes -- FastAPI resolves either automatically): returns a
      `ScopedGraphStore` so ingestion/analytics/search only ever see that
      one investigation's data. See `app/db/graph_store.py`.
    """
    if investigation_id:
        return ScopedGraphStore(store, investigation_id)
    return store


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
