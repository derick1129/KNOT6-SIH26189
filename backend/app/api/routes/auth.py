from fastapi import APIRouter, HTTPException, status

from app.core.security import authenticate, create_access_token
from app.models.schemas import LoginRequest, LoginResponse
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    user = authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password.")
    token = create_access_token(user)
    audit.log(actor=user.username, action="LOGIN")
    return LoginResponse(access_token=token, role=user.role, full_name=user.full_name)
