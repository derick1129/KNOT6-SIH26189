from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import authenticate, create_access_token
from app.models.schemas import LoginRequest, LoginResponse
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate(payload.username, payload.password, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password.")
    token = create_access_token(user)
    audit.log(actor=user.username, action="LOGIN")
    return LoginResponse(access_token=token, role=user.role, full_name=user.full_name)
