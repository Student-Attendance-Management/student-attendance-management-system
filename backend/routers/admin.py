"""Attendance rules and audit log (SAM-F-017/018, SAM-SR-005)."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from ..database import audit, db
from ..security import auth

router = APIRouter()


# ---------- Rules & audit (SAM-F-017/018) ----------
class Rules(BaseModel):
    threshold: float
    correction_hours: int


@router.get("/api/rules")
def get_rules(user=Depends(auth("Admin", "Faculty"))):
    con = db(); r = dict(con.execute("SELECT threshold, correction_hours FROM rules").fetchone()); con.close(); return r


@router.put("/api/rules")
def set_rules(b: Rules, user=Depends(auth("Admin"))):
    if not 0 <= b.threshold <= 100 or b.correction_hours < 0:
        raise HTTPException(400, "Invalid data")
    con = db(); con.execute("UPDATE rules SET threshold=?, correction_hours=?", (b.threshold, b.correction_hours))
    audit(con, user, "update", "rules", 1); con.commit(); con.close(); return b


@router.get("/api/audit")
def get_audit(user=Depends(auth("Admin"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]; con.close(); return r
