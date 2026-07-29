from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import create_access_token, current_user, verify_password
from ..models.user import User
from ..schemas.auth import LoginRequest, LoginResponse, UserRead
router = APIRouter(prefix="/api/auth", tags=["auth"])
@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, detail={"code":"authentication_required","message":"Invalid username or password"})
    return {"access_token": create_access_token(user), "token_type":"bearer", "user":user}
@router.get("/me", response_model=UserRead)
def me(user: User = Depends(current_user)): return user
