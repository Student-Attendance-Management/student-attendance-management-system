"""Password hashing (SAM-SR-002), sessions and role checks (SAM-F-002, SAM-SR-003/006)."""
import hashlib, secrets, time
from typing import Optional

from fastapi import Header, HTTPException

from .config import SESSION_TIMEOUT

TOKENS: dict = {}  # token -> {user, last}


def hash_pw(pw: str, salt: Optional[str] = None) -> str:  # salted one-way hash
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw: str, stored: str) -> bool:
    salt, _ = stored.split("$")
    return secrets.compare_digest(hash_pw(pw, salt), stored)


def auth(*roles):  # deny by default
    def dep(authorization: str = Header(default="")):
        token = authorization.replace("Bearer ", "")
        s = TOKENS.get(token)
        if not s:
            raise HTTPException(401, "Not authenticated")
        if time.time() - s["last"] > SESSION_TIMEOUT:
            TOKENS.pop(token, None)
            raise HTTPException(401, "Session expired")
        s["last"] = time.time()
        if roles and s["user"]["role"] not in roles:
            raise HTTPException(403, "Unauthorized")
        return s["user"]
    return dep
