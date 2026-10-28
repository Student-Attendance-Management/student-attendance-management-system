"""SAMS entry point. Layers: routers (HTTP) -> security / database (helpers) -> SQLite."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .database import db, init_db  # noqa: F401  (re-exported for seed.py)
from .routers import admin, attendance, auth, master_data, reports
from .security import TOKENS, hash_pw  # noqa: F401

app = FastAPI(title="Student Attendance Management System")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for _m in (auth, master_data, attendance, reports, admin):
    app.include_router(_m.router)


@app.on_event("startup")
def _startup():
    init_db()


_FRONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "index.html")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(_FRONT)
