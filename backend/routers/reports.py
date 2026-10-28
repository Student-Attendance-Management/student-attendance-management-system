"""Reports, filters, low-attendance alerts, CSV export (SAM-F-014..017)."""
import csv, io
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..database import db
from ..security import auth
from .attendance import percentage

router = APIRouter()


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


@router.get("/api/attendance/report")
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


@router.get("/api/attendance/low")
def low_attendance(classId: Optional[int] = None, user=Depends(auth("Admin", "Faculty"))):
    con = db(); th = con.execute("SELECT threshold FROM rules").fetchone()[0]
    out = []
    for st in con.execute("SELECT * FROM students WHERE status='active'" + (" AND class_id=?" if classId else ""),
                          [classId] if classId else []).fetchall():
        p = percentage(con, st["id"])
        if p["conducted"] and p["percentage"] < th:
            out.append({"studentId": st["id"], "name": st["name"], **p})
    con.close(); return {"threshold": th, "students": out}
