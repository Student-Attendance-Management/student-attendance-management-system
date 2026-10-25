# Student Attendance Management System (SAMS)

FastAPI + SQLite, layered per the Architecture doc. Docs (SRS, SAD, STP) are in the repo root.

## Run
```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000/docs for the interactive API (use **Authorize** with the login token).
Default admin: `admin` / `admin123` (override with `SAMS_ADMIN_PASSWORD`).

## Test
```bash
python -m pytest -q
```

## Config (env vars)
`SAMS_DB` (db file), `SAMS_SESSION_TIMEOUT` (seconds, default 1800), `SAMS_ADMIN_PASSWORD`.

## Requirement coverage
| SRS ID | Where |
|---|---|
| SAM-F-001/002, SR-003 | `/api/auth/login`, `auth()` role dependency |
| SAM-F-003..006 | `/api/students`, `/api/faculty`, `/api/classes`, `/api/subjects`, `/api/assignments` |
| SAM-F-007..010 | `/api/attendance/sessions`, `/mark`, `/correct`, UNIQUE(session, student) |
| SAM-F-011..013 | `/api/attendance/percentage`, `/history`, `/summary` |
| SAM-F-014..017 | `/api/attendance/report` (+`export=csv`), `/low`, filters, `/api/rules` |
| SAM-F-018, SR-005 | `audit` table, `/api/audit` |
| SAM-NF-003, SR-002 | salted PBKDF2 password hashes |
| SAM-SR-004 | parameterized SQL, input validation |
| SAM-SR-006 | session timeout |

## Not yet / deviations
HTTPS is deployment config (SAM-SR-001). Web UI is minimal (Swagger). Load/availability NFRs are test-verified, not coded.
