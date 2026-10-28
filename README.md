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
Load/availability NFRs are test-verified, not coded.

## Code layout (SAM-NF-006)
```
backend/
  main.py          app setup, CORS, router wiring, serves the UI
  config.py        environment settings
  security.py      password hashing, sessions, role checks
  database.py      schema, connections, audit log, safe inserts
  routers/         auth, master_data, attendance, reports, admin
frontend/index.html   single-page UI
seed.py               demo data loader
```

## HTTPS / TLS (SAM-SR-001)
```bash
python run_https.py        # https://127.0.0.1:8443
```
Generates a self-signed dev certificate on first run (`certs/`, git-ignored). The browser shows a warning for
self-signed certs: Advanced -> Proceed. In production, terminate TLS at a reverse proxy (nginx/Caddy) with a real
certificate and forward to `uvicorn backend.main:app`.
