"""Login and logout (SAM-F-001)."""
import secrets, time

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from ..database import db
from ..security import TOKENS, auth, check_pw

router = APIRouter()


# ---------- Auth (SAM-F-001) ----------
class Login(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
def login(b: Login):
    con = db()
    u = con.execute("SELECT * FROM users WHERE username=? AND status='active'", (b.username,)).fetchone()
    con.close()
    if not u or not check_pw(b.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_urlsafe(32)
    TOKENS[token] = {"user": dict(u), "last": time.time()}
    return {"token": token, "role": u["role"]}


@router.post("/api/auth/logout")
def logout(authorization: str = Header(default=""), user=Depends(auth())):
    TOKENS.pop(authorization.replace("Bearer ", ""), None)
    return {"status": "logged out"}
