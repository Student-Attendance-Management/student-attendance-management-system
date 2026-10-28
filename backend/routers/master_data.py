"""Students, faculty, classes, subjects, assignments (SAM-F-003..006)."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from ..database import audit, db, insert
from ..security import auth, hash_pw

router = APIRouter()


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


@router.post("/api/classes")
def add_class(b: NewClass, user=Depends(auth("Admin"))):
    con = db(); i = insert(con, "INSERT INTO classes(name,term) VALUES(?,?)", (b.name, b.term))
    audit(con, user, "create", "class", i); con.commit(); con.close(); return {"id": i}


@router.get("/api/classes")
def list_classes(user=Depends(auth("Admin", "Faculty"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM classes")]; con.close(); return r


@router.post("/api/subjects")
def add_subject(b: NewSubject, user=Depends(auth("Admin"))):
    con = db(); i = insert(con, "INSERT INTO subjects(code,name) VALUES(?,?)", (b.code, b.name))
    audit(con, user, "create", "subject", i); con.commit(); con.close(); return {"id": i}


@router.get("/api/subjects")
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


@router.post("/api/students")
def add_student(b: NewPerson, user=Depends(auth("Admin"))):
    return make_person("students", "Student", b, user)


@router.get("/api/students")
def list_students(q: str = "", class_id: Optional[int] = None, user=Depends(auth("Admin", "Faculty"))):
    con = db()
    sql, args = "SELECT * FROM students WHERE (name LIKE ? OR email LIKE ?)", [f"%{q}%", f"%{q}%"]
    if class_id:
        sql += " AND class_id=?"; args.append(class_id)
    r = [dict(x) for x in con.execute(sql, args)]; con.close(); return r


@router.patch("/api/students/{sid}/status")
def student_status(sid: int, active: bool, user=Depends(auth("Admin"))):
    con = db(); st = "active" if active else "inactive"
    con.execute("UPDATE students SET status=? WHERE id=?", (st, sid))
    con.execute("UPDATE users SET status=? WHERE role='Student' AND ref_id=?", (st, sid))
    audit(con, user, f"set_{st}", "student", sid); con.commit(); con.close(); return {"status": st}


@router.post("/api/faculty")
def add_faculty(b: NewPerson, user=Depends(auth("Admin"))):
    return make_person("faculty", "Faculty", b, user)


@router.get("/api/faculty")
def list_faculty(user=Depends(auth("Admin"))):
    con = db(); r = [dict(x) for x in con.execute("SELECT * FROM faculty")]; con.close(); return r


@router.post("/api/assignments")
def assign(b: NewAssignment, user=Depends(auth("Admin"))):
    con = db()
    i = insert(con, "INSERT INTO assignments(faculty_id,subject_id,class_id) VALUES(?,?,?)",
               (b.faculty_id, b.subject_id, b.class_id))
    audit(con, user, "create", "assignment", i); con.commit(); con.close(); return {"id": i}
