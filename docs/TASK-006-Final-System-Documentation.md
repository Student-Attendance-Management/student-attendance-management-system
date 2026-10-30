# Student Attendance Management System
## Final System Documentation

**Purpose:** User and maintainer guide for the implementation represented by the supplied repository snapshot.  
**Status:** Documentation draft prepared for TASK-006 review  
**Snapshot reviewed:** 30 October 2026

> This guide reflects the files supplied for review. It is not a production deployment approval. Test outcomes below are transcribed from the project's recorded regression/security report; they were not rerun while preparing this guide.

## 1. What the system does

SAMS provides role-based attendance workflows for:

- **Administrators:** manage classes, subjects, students, faculty, and faculty assignments; configure attendance threshold/correction window; view audit records and reports.
- **Faculty:** work with assigned classes, create sessions, mark or correct attendance within policy, review summaries/reports, and see low-attendance students.
- **Students:** sign in and view their own attendance history and percentage.

The system currently supports Present/Absent attendance values, CSV report export, and low-attendance identification. Email/push alerts and PDF report export were not found in the supplied implementation.

## 2. Requirements

- The CI workflow uses Python 3.12; use Python 3.12 to match CI. The repository does not declare a minimum supported Python version.
- Install packages from `requirements.txt`.
- The project uses SQLite, so no separate database server setup is required for the default local run.

## 3. Run locally

From the repository root:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/` for the user interface or `http://127.0.0.1:8000/docs` for the interactive API documentation. The app initializes the SQLite schema and default rules on startup. By default, the database is `sams.db` in the current working directory.

### Optional local HTTPS

```bash
python run_https.py
```

This serves on `https://127.0.0.1:8443` and creates a self-signed development certificate in `certs/` the first time. Browsers will show a certificate warning because it is self-signed. This is for local development only. The supplied project README recommends a reverse proxy with a real certificate for production TLS.

## 4. Configuration

| Environment variable | Purpose | Default |
|---|---|---|
| `SAMS_DB` | SQLite database file path | `sams.db` |
| `SAMS_SESSION_TIMEOUT` | Inactivity timeout in seconds | `1800` |
| `SAMS_ADMIN_PASSWORD` | Password for the default admin account created at startup | `admin123` |

Set a strong `SAMS_ADMIN_PASSWORD` before using the system beyond a disposable demo. Do not commit secrets or real student data to the repository.

## 5. Demo data and accounts

Run `python seed.py` from the repository root to load sample classes, subjects, students, faculty, assignments, and attendance. The script skips loading if student data already exists.

The source currently defines these demo credentials:

- Admin: username `admin`; password is `SAMS_ADMIN_PASSWORD` or the default `admin123`.
- Faculty: `kulkarni@faculty.test` / `faculty123`.
- Student: `aarav@student.test` / `student123`.

These are sample credentials only. Do not reuse them for real users. If data already exists, the seed script exits without changing it.

## 6. Main workflows

### Sign in

Use the login screen with an active account. The API returns a bearer token and role. The interface displays role-appropriate functions. Logout invalidates the current process-local token.

### Administrator setup

Create classes and subjects, add student and faculty profiles, then assign faculty to a class and subject. Configure the low-attendance threshold and faculty correction window in the Rules area. The initial database defaults are 75 percent and 48 hours.

### Take attendance

Authorized Admin or assigned Faculty creates an attendance session with assignment, date, and period. The session roster is retrieved, then Present/Absent records are submitted. Duplicate records for a student/session are rejected. Faculty may correct records within the configured correction window; Admin corrections bypass this time-window check in the supplied code. Important changes are recorded in the audit table.

### Review attendance

Students can view only their own history and percentage. Faculty reports and summaries are limited to assigned classes/subjects. Admin and Faculty can view attendance reports and low-attendance results. Report rows can be downloaded as CSV.

## 7. API overview

FastAPI's interactive endpoint reference is at `/docs` while the app is running. Main routes include:

- Authentication: `POST /api/auth/login`, `POST /api/auth/logout`
- Academic setup: `/api/classes`, `/api/subjects`, `/api/students`, `/api/faculty`, `/api/assignments`
- Attendance: `/api/attendance/sessions`, `/api/attendance/mark`, `/api/attendance/correct`
- Student view and faculty summary: `/api/attendance/percentage`, `/api/attendance/history`, `/api/attendance/summary`
- Reporting: `/api/attendance/report`, `/api/attendance/low`
- Configuration and audit: `/api/rules`, `/api/audit`

Protected routes require `Authorization: Bearer <token>`. The `/docs` interface includes an **Authorize** control for entering the token.

## 8. Data and calculation notes

Attendance percentage is computed as the number of Present records divided by recorded attendance records, multiplied by 100, rounded to two decimal places. No records produces 0 percent. Low attendance means strictly below the configured threshold. The database has uniqueness constraints for assignments, sessions by assignment/date/period, and records by session/student.

## 9. Tests and CI

Run the automated test suite with:

```bash
python -m pytest -q
```

GitHub Actions is configured to install the requirements and run pytest on pushes to `main` and pull requests. The supplied TASK-005 report records two automated tests passing and 18 warnings. It also records selected manual regression checks, including auth, attendance workflows, reports, and role checks.

The same report notes important limits: HTTPS deployment testing was pending; concurrency testing covered only five requests; SQL-injection checking was a smoke test; one subject-creation attempt initially returned HTTP 500 before succeeding on retry. These results are not proof of 100-user capacity, 99% availability, or complete security assurance.

## 10. Known limitations and items not demonstrated

- The supplied code does not include email or push notifications; low-attendance identification is an API result.
- CSV export is present; PDF export was not found.
- Create/list operations are present for classes, subjects, and faculty. Existing-profile update operations were not found. Students can be activated/deactivated; a general student profile update route was not found.
- Tokens are stored in process memory and are cleared on server restart.
- CORS is configured to allow all origins in this snapshot; production configuration should be reviewed.
- The default admin credential is unsafe for a real deployment and must be overridden.
- A self-signed development certificate is not production TLS configuration.
- Mobile viewport, deployment backup/recovery, monthly availability, and target-scale load results were not supplied.

These are implementation/documentation gaps to report accurately. This guide does not claim those items are complete.

## 11. Repository map

```text
backend/                 FastAPI app, configuration, security, SQLite, routers
frontend/index.html       Single-page browser UI
tests/test_flow.py       Automated API/UI flow tests
seed.py                   Demo data loader
run_https.py              Local self-signed HTTPS runner
requirements.txt          Python dependencies
.github/workflows/ci.yml  GitHub Actions test workflow
docs/final-website-demonstration.md
                          Link to the final website demonstration
```

## 12. Document review and release note

This guide was checked against the supplied README, backend modules, frontend, test file, CI workflow, demo-data loader, HTTPS runner, SAD, STP, and TASK-005 recorded test report. The code snapshot was inspected; tests and a live deployed system were not independently run. Update the version/status and review date when the project owner records their final review. Do not mark TASK-006 Done until the as-built architecture and final documentation are committed and the review is recorded.


