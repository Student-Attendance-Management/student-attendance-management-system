"""Sessions, marking, correction, percentage, history, summary (SAM-F-007..013)."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from ..database import audit, db, insert
from ..security import auth

router = APIRouter()


# ---------- Attendance (SAM-F-007..010) ----------
class NewSession(BaseModel):
    assignment_id: int
    date: str
    period: int


class Mark(BaseModel):
    studentId: int
    status: str


class MarkReq(BaseModel):
    sessionId: int
    records: list[Mark]


def own_assignment(con, user, assignment_id):
    a = con.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Assignment not found")
    if user["role"] == "Faculty" and a["faculty_id"] != user["ref_id"]:
        raise HTTPException(403, "Unauthorized")
    return a


@router.post("/api/attendance/sessions")
def create_session(b: NewSession, user=Depends(auth("Admin", "Faculty"))):
    con = db(); own_assignment(con, user, b.assignment_id)
    i = insert(con, "INSERT INTO att_sessions(assignment_id,date,period,created_at) VALUES(?,?,?,?)",
               (b.assignment_id, b.date, b.period, datetime.utcnow().isoformat()))
    audit(con, user, "create", "att_session", i); con.commit(); con.close(); return {"id": i}


@router.get("/api/attendance/sessions/{sid}/students")
def session_students(sid: int, user=Depends(auth("Admin", "Faculty"))):
    con = db()
    s = con.execute("SELECT s.*, a.class_id, a.faculty_id FROM att_sessions s JOIN assignments a "
                    "ON a.id=s.assignment_id WHERE s.id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Not found")
    own_assignment(con, user, s["assignment_id"])
    r = [dict(x) for x in con.execute("SELECT id,name FROM students WHERE class_id=? AND status='active'",
                                      (s["class_id"],))]
    con.close(); return r


@router.post("/api/attendance/mark")
def mark(b: MarkReq, user=Depends(auth("Admin", "Faculty"))):
    con = db()
    s = con.execute("SELECT * FROM att_sessions WHERE id=?", (b.sessionId,)).fetchone()
    if not s:
        raise HTTPException(404, "Session not found")
    a = own_assignment(con, user, s["assignment_id"])
    for r in b.records:
        if r.status not in ("Present", "Absent"):
            raise HTTPException(400, "Invalid data")
        st = con.execute("SELECT 1 FROM students WHERE id=? AND class_id=?", (r.studentId, a["class_id"])).fetchone()
        if not st:
            raise HTTPException(400, "Student not enrolled in this class")
        if con.execute("SELECT 1 FROM records WHERE session_id=? AND student_id=?", (b.sessionId, r.studentId)).fetchone():
            raise HTTPException(409, "Duplicate attendance")
        i = insert(con, "INSERT INTO records(session_id,student_id,status,updated_at) VALUES(?,?,?,?)",
                   (b.sessionId, r.studentId, r.status, datetime.utcnow().isoformat()))
        audit(con, user, f"mark_{r.status}", "record", i)
    con.commit(); con.close(); return {"status": "saved", "count": len(b.records)}


class Correct(BaseModel):
    sessionId: int
    studentId: int
    status: str


@router.put("/api/attendance/correct")
def correct(b: Correct, user=Depends(auth("Admin", "Faculty"))):
    if b.status not in ("Present", "Absent"):
        raise HTTPException(400, "Invalid data")
    con = db()
    rec = con.execute("SELECT r.*, s.created_at AS sc, s.assignment_id FROM records r JOIN att_sessions s "
                      "ON s.id=r.session_id WHERE r.session_id=? AND r.student_id=?",
                      (b.sessionId, b.studentId)).fetchone()
    if not rec:
        raise HTTPException(404, "Record not found")
    own_assignment(con, user, rec["assignment_id"])
    hrs = con.execute("SELECT correction_hours FROM rules").fetchone()[0]
    if user["role"] != "Admin" and datetime.utcnow() - datetime.fromisoformat(rec["sc"]) > timedelta(hours=hrs):
        raise HTTPException(403, "Correction period over")
    con.execute("UPDATE records SET status=?, updated_at=? WHERE id=?",
                (b.status, datetime.utcnow().isoformat(), rec["id"]))
    audit(con, user, f"correct_{rec['status']}_to_{b.status}", "record", rec["id"])
    con.commit(); con.close(); return {"status": b.status}


# ---------- Calculation & views (SAM-F-011..013) ----------
def percentage(con, student_id, subject_id=None):  # single centralized formula
    sql = ("SELECT COUNT(*) c, SUM(r.status='Present') p FROM records r JOIN att_sessions s ON s.id=r.session_id "
           "JOIN assignments a ON a.id=s.assignment_id WHERE r.student_id=?")
    args = [student_id]
    if subject_id:
        sql += " AND a.subject_id=?"; args.append(subject_id)
    row = con.execute(sql, args).fetchone()
    conducted, attended = row["c"], row["p"] or 0
    pct = round(attended * 100 / conducted, 2) if conducted else 0.0
    return {"percentage": pct, "attended": attended, "conducted": conducted}


def target_student(user, student_id):  # students only see themselves
    if user["role"] == "Student":
        return user["ref_id"]
    if not student_id:
        raise HTTPException(400, "studentId required")
    return student_id


@router.get("/api/attendance/percentage")
def get_pct(studentId: Optional[int] = None, subjectId: Optional[int] = None, user=Depends(auth())):
    sid = target_student(user, studentId)
    con = db()
    if not con.execute("SELECT 1 FROM students WHERE id=?", (sid,)).fetchone():
        raise HTTPException(404, "Not found")
    r = percentage(con, sid, subjectId); con.close(); return r


@router.get("/api/attendance/history")
def history(studentId: Optional[int] = None, user=Depends(auth())):
    sid = target_student(user, studentId)
    con = db()
    r = [dict(x) for x in con.execute(
        "SELECT s.date, s.period, sub.name AS subject, r.status FROM records r JOIN att_sessions s ON s.id=r.session_id "
        "JOIN assignments a ON a.id=s.assignment_id JOIN subjects sub ON sub.id=a.subject_id "
        "WHERE r.student_id=? ORDER BY s.date DESC, s.period", (sid,))]
    con.close(); return r


@router.get("/api/attendance/summary")  # faculty dashboard
def faculty_summary(user=Depends(auth("Faculty", "Admin"))):
    con = db()
    sql = ("SELECT a.id AS assignment_id, sub.name AS subject, c.name AS class, COUNT(DISTINCT s.id) sessions "
           "FROM assignments a JOIN subjects sub ON sub.id=a.subject_id JOIN classes c ON c.id=a.class_id "
           "LEFT JOIN att_sessions s ON s.assignment_id=a.id")
    args = []
    if user["role"] == "Faculty":
        sql += " WHERE a.faculty_id=?"; args.append(user["ref_id"])
    r = [dict(x) for x in con.execute(sql + " GROUP BY a.id", args)]; con.close(); return r
