"""SQLite access: schema, connections, audit logging (SAM-F-018), safe inserts (SAM-NF-004)."""
import os, sqlite3
from datetime import datetime

from fastapi import HTTPException

from .config import DB_PATH
from .security import hash_pw

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


def audit(con, user, action, entity, entity_id):
    con.execute("INSERT INTO audit(user_id,action,entity,entity_id,ts) VALUES(?,?,?,?,?)",
                (user["id"], action, entity, entity_id, datetime.utcnow().isoformat()))


def insert(con, sql, args):
    try:
        return con.execute(sql, args).lastrowid
    except sqlite3.IntegrityError as e:
        raise HTTPException(409, f"Duplicate or invalid reference: {e}")
