import os, tempfile

os.environ["SAMS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["SAMS_SESSION_TIMEOUT"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app, TOKENS  # noqa: E402
import time  # noqa: E402


def login(c, u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    return r, {"Authorization": f"Bearer {r.json().get('token', '')}"}


def test_full_flow():
    with TestClient(app) as c:
        os.environ["SAMS_SESSION_TIMEOUT"] = "1000"
        import backend.security as m; m.SESSION_TIMEOUT = 1000
        assert login(c, "admin", "wrong")[0].status_code == 401
        _, A = login(c, "admin", "admin123")
        cl = c.post("/api/classes", json={"name": "CSE-A", "term": "S5"}, headers=A).json()["id"]
        sub = c.post("/api/subjects", json={"code": "SE101", "name": "SE"}, headers=A).json()["id"]
        s1 = c.post("/api/students", json={"name": "A", "email": "a@x.com", "password": "pass123", "class_id": cl}, headers=A).json()["id"]
        s2 = c.post("/api/students", json={"name": "B", "email": "b@x.com", "password": "pass123", "class_id": cl}, headers=A).json()["id"]
        f = c.post("/api/faculty", json={"name": "F", "email": "f@x.com", "password": "pass123"}, headers=A).json()["id"]
        asg = c.post("/api/assignments", json={"faculty_id": f, "subject_id": sub, "class_id": cl}, headers=A).json()["id"]

        _, F = login(c, "f@x.com", "pass123")
        _, S = login(c, "a@x.com", "pass123")
        sess = c.post("/api/attendance/sessions", json={"assignment_id": asg, "date": "2026-10-26", "period": 1}, headers=F).json()["id"]
        body = {"sessionId": sess, "records": [{"studentId": s1, "status": "Present"}, {"studentId": s2, "status": "Absent"}]}
        assert c.post("/api/attendance/mark", json=body, headers=S).status_code == 403   # student cannot mark
        assert c.post("/api/attendance/mark", json=body, headers=F).status_code == 200
        assert c.post("/api/attendance/mark", json=body, headers=F).status_code == 409   # duplicate
        assert c.get("/api/attendance/percentage", headers=S).json()["percentage"] == 100.0
        assert c.get("/api/attendance/percentage", params={"studentId": s2}, headers=F).json()["percentage"] == 0.0
        low = c.get("/api/attendance/low", headers=F).json()
        assert [x["studentId"] for x in low["students"]] == [s2]
        assert c.put("/api/attendance/correct", json={"sessionId": sess, "studentId": s2, "status": "Present"}, headers=F).status_code == 200
        assert c.get("/api/attendance/percentage", params={"studentId": s2}, headers=F).json()["percentage"] == 100.0
        assert c.get("/api/attendance/report", params={"export": "csv"}, headers=F).status_code == 200
        assert c.get("/api/audit", headers=F).status_code == 403
        assert len(c.get("/api/audit", headers=A).json()) > 0
        assert c.post("/api/auth/logout", headers=S).status_code == 200
        assert c.get("/api/attendance/history", headers=S).status_code == 401


def test_session_timeout():
    with TestClient(app) as c:
        import backend.security as m
        _, A = login(c, "admin", "admin123")
        tok = A["Authorization"].split()[1]
        TOKENS[tok]["last"] = time.time() - m.SESSION_TIMEOUT - 5
        assert c.get("/api/rules", headers=A).status_code == 401


def test_ui_served():
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200 and "Student Attendance" in r.text
