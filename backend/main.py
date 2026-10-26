"""SAMS backend: FastAPI + SQLite. Layered: routes -> helpers -> DB."""
import csv, hashlib, io, os, secrets, sqlite3, time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

DB_PATH = os.environ.get("SAMS_DB", "sams.db")
SESSION_TIMEOUT = int(os.environ.get("SAMS_SESSION_TIMEOUT", "1800"))  # SAM-SR-006

app = FastAPI(title="Student Attendance Management System")
TOKENS: dict = {}  # token -> {user, last}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL, status TEXT DEFAULT 'active', ref_id INTEGER);
CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, name TEXT NOT NULL, term TEXT);
CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  class_id INTEGER REFERENCES classes(id), status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS faculty(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY, faculty_id INTEGER NOT NULL REFERENCES faculty(id),
  subject_id INTEGER NOT NULL REFERENCES subjects(id), class_id INTEGER NOT NULL REFERENCES classes(id),
  UNIQUE(faculty_id, subject_id, class_id));
CREATE TABLE IF NOT EXISTS att_sessions(id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL REFERENCES assignments(id),
  date TEXT NOT NULL, period INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(assignment_id, date, period));
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES att_sessions(id),
  student_id INTEGER NOT NULL REFERENCES students(id), status TEXT NOT NULL CHECK(status IN ('Present','Absent')),
  updated_at TEXT NOT NULL, UNIQUE(session_id, student_id));  -- SAM-F-009
CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY CHECK(id=1), threshold REAL, correction_hours INTEGER);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, entity TEXT,
  entity_id INTEGER, ts TEXT);
"""


def hash_pw(pw: str, salt: Optional[str] = None) -> str:  # salted one-way hash (SAM-SR-002)
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw: str, stored: str) -> bool:
    salt, _ = stored.split("$")
    return secrets.compare_digest(hash_pw(pw, salt), stored)


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    con = db()
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO rules VALUES(1, 75, 48)")
    if not con.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        con.execute("INSERT INTO users(username,password_hash,role) VALUES('admin',?, 'Admin')",
                    (hash_pw(os.environ.get("SAMS_ADMIN_PASSWORD", "admin123")),))
    con.commit(); con.close()


@app.on_event("startup")
def _startup():
    init_db()


def audit(con, user, action, entity, entity_id):  # SAM-F-018
    con.execute("INSERT INTO audit(user_id,action,entity,entity_id,ts) VALUES(?,?,?,?,?)",
                (user["id"], action, entity, entity_id, datetime.utcnow().isoformat()))


def auth(*roles):  # SAM-F-002 / SR-003: deny by default
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


# ---------- Auth (SAM-F-001) ----------
class Login(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(b: Login):
    con = db()
    u = con.execute("SELECT * FROM users WHERE username=? AND status='active'", (b.username,)).fetchone()
    con.close()
    if not u or not check_pw(b.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_urlsafe(32)
    TOKENS[token] = {"user": dict(u), "last": time.time()}
    return {"token": token, "role": u["role"]}


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default=""), user=Depends(auth())):
    TOKENS.pop(authorization.replace("Bearer ", ""), None)
    return {"status": "logged out"}


# ---------- Master data (SAM-F-003..006) ----------
class NewClass(BaseModel):
    name: str
    term: str = ""


class NewSubject(BaseModel):
    code: str
    name: str


class NewPerson(BaseModel):
    name: str
    email: str
    password: str
    class_id: Optional[int] = None


class NewAssignment(BaseModel):
    faculty_id: int
    subject_id: int
    class_id: int


def insert(con, sql, args):
    try:
        return con.execute(sql, args).lastrowid
    except sqlite3.IntegrityError as e:
        raise HTTPException(409, f"Duplicate or invalid reference: {e}")


@app.post("/api/classes")
def add_class(b: NewClass, user=Depends(auth("Admin"))):
    con = db(); i = insert(con, "INSERT INTO classes(name,term) VALUES(?,?)", (b.name, b.term))
    audit(con, user, "create", "class", i); con.commit(); con.close(); return {"id": i}


@app.get("/api/classes")
def list_classes(user=Depends(auth("Admin", "Faculty"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM classes")]; con.close(); return r


@app.post("/api/subjects")
def add_subject(b: NewSubject, user=Depends(auth("Admin"))):
    con = db(); i = insert(con, "INSERT INTO subjects(code,name) VALUES(?,?)", (b.code, b.name))
    audit(con, user, "create", "subject", i); con.commit(); con.close(); return {"id": i}


@app.get("/api/subjects")
def list_subjects(user=Depends(auth("Admin", "Faculty"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM subjects")]; con.close(); return r


def make_person(table, role, b: NewPerson, user):
    if not b.name.strip() or "@" not in b.email or len(b.password) < 6:
        raise HTTPException(400, "Invalid data")
    con = db()
    if table == "students":
        i = insert(con, "INSERT INTO students(name,email,class_id) VALUES(?,?,?)", (b.name, b.email, b.class_id))
    else:
        i = insert(con, "INSERT INTO faculty(name,email) VALUES(?,?)", (b.name, b.email))
    insert(con, "INSERT INTO users(username,password_hash,role,ref_id) VALUES(?,?,?,?)",
           (b.email, hash_pw(b.password), role, i))
    audit(con, user, "create", table, i); con.commit(); con.close()
    return {"id": i}


@app.post("/api/students")
def add_student(b: NewPerson, user=Depends(auth("Admin"))):
    return make_person("students", "Student", b, user)


@app.get("/api/students")
def list_students(q: str = "", class_id: Optional[int] = None, user=Depends(auth("Admin", "Faculty"))):
    con = db()
    sql, args = "SELECT * FROM students WHERE (name LIKE ? OR email LIKE ?)", [f"%{q}%", f"%{q}%"]
    if class_id:
        sql += " AND class_id=?"; args.append(class_id)
    r = [dict(x) for x in con.execute(sql, args)]; con.close(); return r


@app.patch("/api/students/{sid}/status")
def student_status(sid: int, active: bool, user=Depends(auth("Admin"))):
    con = db(); st = "active" if active else "inactive"
    con.execute("UPDATE students SET status=? WHERE id=?", (st, sid))
    con.execute("UPDATE users SET status=? WHERE role='Student' AND ref_id=?", (st, sid))
    audit(con, user, f"set_{st}", "student", sid); con.commit(); con.close(); return {"status": st}


@app.post("/api/faculty")
def add_faculty(b: NewPerson, user=Depends(auth("Admin"))):
    return make_person("faculty", "Faculty", b, user)


@app.get("/api/faculty")
def list_faculty(user=Depends(auth("Admin"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM faculty")]; con.close(); return r


@app.post("/api/assignments")
def assign(b: NewAssignment, user=Depends(auth("Admin"))):
    con = db()
    i = insert(con, "INSERT INTO assignments(faculty_id,subject_id,class_id) VALUES(?,?,?)",
               (b.faculty_id, b.subject_id, b.class_id))
    audit(con, user, "create", "assignment", i); con.commit(); con.close(); return {"id": i}


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


@app.post("/api/attendance/sessions")
def create_session(b: NewSession, user=Depends(auth("Admin", "Faculty"))):
    con = db(); own_assignment(con, user, b.assignment_id)
    i = insert(con, "INSERT INTO att_sessions(assignment_id,date,period,created_at) VALUES(?,?,?,?)",
               (b.assignment_id, b.date, b.period, datetime.utcnow().isoformat()))
    audit(con, user, "create", "att_session", i); con.commit(); con.close(); return {"id": i}


@app.get("/api/attendance/sessions/{sid}/students")
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


@app.post("/api/attendance/mark")
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


@app.put("/api/attendance/correct")
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


@app.get("/api/attendance/percentage")
def get_pct(studentId: Optional[int] = None, subjectId: Optional[int] = None, user=Depends(auth())):
    sid = target_student(user, studentId)
    con = db()
    if not con.execute("SELECT 1 FROM students WHERE id=?", (sid,)).fetchone():
        raise HTTPException(404, "Not found")
    r = percentage(con, sid, subjectId); con.close(); return r


@app.get("/api/attendance/history")
def history(studentId: Optional[int] = None, user=Depends(auth())):
    sid = target_student(user, studentId)
    con = db()
    r = [dict(x) for x in con.execute(
        "SELECT s.date, s.period, sub.name AS subject, r.status FROM records r JOIN att_sessions s ON s.id=r.session_id "
        "JOIN assignments a ON a.id=s.assignment_id JOIN subjects sub ON sub.id=a.subject_id "
        "WHERE r.student_id=? ORDER BY s.date DESC, s.period", (sid,))]
    con.close(); return r


@app.get("/api/attendance/summary")  # faculty dashboard
def faculty_summary(user=Depends(auth("Faculty", "Admin"))):
    con = db()
    sql = ("SELECT a.id AS assignment_id, sub.name AS subject, c.name AS class, COUNT(DISTINCT s.id) sessions "
           "FROM assignments a JOIN subjects sub ON sub.id=a.subject_id JOIN classes c ON c.id=a.class_id "
           "LEFT JOIN att_sessions s ON s.assignment_id=a.id")
    args = []
    if user["role"] == "Faculty":
        sql += " WHERE a.faculty_id=?"; args.append(user["ref_id"])
    r = [dict(x) for x in con.execute(sql + " GROUP BY a.id", args)]; con.close(); return r


# ---------- Reports, filters, low attendance, export (SAM-F-014..017) ----------
def report_rows(con, user, class_id, subject_id, date_from, date_to, student_id=None, status=None):
    sql = ("SELECT st.id student_id, st.name student, c.name class, sub.name subject, s.date, s.period, r.status "
           "FROM records r JOIN att_sessions s ON s.id=r.session_id JOIN assignments a ON a.id=s.assignment_id "
           "JOIN students st ON st.id=r.student_id JOIN classes c ON c.id=a.class_id "
           "JOIN subjects sub ON sub.id=a.subject_id WHERE 1=1")
    args = []
    if user["role"] == "Faculty":
        sql += " AND a.faculty_id=?"; args.append(user["ref_id"])
    for col, val in (("a.class_id", class_id), ("a.subject_id", subject_id), ("s.date>=", date_from),
                     ("s.date<=", date_to), ("r.student_id", student_id), ("r.status", status)):
        if val is not None and val != "":
            sql += f" AND {col}{'' if col.endswith('=') else '='}?"; args.append(val)
    return [dict(x) for x in con.execute(sql + " ORDER BY s.date, s.period", args)]


@app.get("/api/attendance/report")
def report(classId: Optional[int] = None, subjectId: Optional[int] = None, dateFrom: str = "", dateTo: str = "",
           studentId: Optional[int] = None, status: Optional[str] = None, export: Optional[str] = None,
           user=Depends(auth("Admin", "Faculty"))):
    con = db(); rows = report_rows(con, user, classId, subjectId, dateFrom, dateTo, studentId, status); con.close()
    if export == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["empty"])
        w.writeheader(); w.writerows(rows)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=attendance_report.csv"})
    return rows


@app.get("/api/attendance/low")
def low_attendance(classId: Optional[int] = None, user=Depends(auth("Admin", "Faculty"))):
    con = db(); th = con.execute("SELECT threshold FROM rules").fetchone()[0]
    out = []
    for st in con.execute("SELECT * FROM students WHERE status='active'" + (" AND class_id=?" if classId else ""),
                          [classId] if classId else []).fetchall():
        p = percentage(con, st["id"])
        if p["conducted"] and p["percentage"] < th:
            out.append({"studentId": st["id"], "name": st["name"], **p})
    con.close(); return {"threshold": th, "students": out}


# ---------- Rules & audit (SAM-F-017/018) ----------
class Rules(BaseModel):
    threshold: float
    correction_hours: int


@app.get("/api/rules")
def get_rules(user=Depends(auth("Admin", "Faculty"))):
    con = db(); r = dict(con.execute("SELECT threshold, correction_hours FROM rules").fetchone()); con.close(); return r


@app.put("/api/rules")
def set_rules(b: Rules, user=Depends(auth("Admin"))):
    if not 0 <= b.threshold <= 100 or b.correction_hours < 0:
        raise HTTPException(400, "Invalid data")
    con = db(); con.execute("UPDATE rules SET threshold=?, correction_hours=?", (b.threshold, b.correction_hours))
    audit(con, user, "update", "rules", 1); con.commit(); con.close(); return b


@app.get("/api/audit")
def get_audit(user=Depends(auth("Admin"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]; con.close(); return r


# ---------- Frontend ----------
from fastapi.responses import FileResponse  # noqa: E402

_FRONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "index.html")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(_FRONT)
