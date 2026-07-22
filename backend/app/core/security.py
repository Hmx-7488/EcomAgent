"""Minimal dependency-free HS256 JWT and fixed-role authorization."""
import base64, hashlib, hmac, json, os, time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from ..models.user import User

ROLES = {"admin", "operator_content", "customer_service"}
_bearer = HTTPBearer(auto_error=False)
_secret = os.getenv("JWT_SECRET", "ecomagent-local-development-secret")
def _b64(data: bytes) -> str: return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
def _unb64(data: str) -> bytes: return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
def hash_password(password: str) -> str:
    salt = b"ecomagent-p0"; return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()
def verify_password(password: str, encoded: str) -> bool: return hmac.compare_digest(hash_password(password), encoded)
def create_access_token(user: User) -> str:
    header = _b64(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub":str(user.id),"role":user.role,"exp":int(time.time())+28800}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"
def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if not credentials: raise HTTPException(401, detail={"code":"authentication_required","message":"Bearer token required"})
    try:
        header, payload, signature = credentials.credentials.split(".")
        expected = _b64(hmac.new(_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        data = json.loads(_unb64(payload))
        if not hmac.compare_digest(expected, signature) or data["exp"] < time.time(): raise ValueError
        user = db.get(User, int(data["sub"]))
        if not user or not user.is_active: raise ValueError
        return user
    except Exception: raise HTTPException(401, detail={"code":"authentication_required","message":"Invalid or expired token"})
def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles: raise HTTPException(403, detail={"code":"permission_denied","message":"Role is not allowed"})
        return user
    return dependency
