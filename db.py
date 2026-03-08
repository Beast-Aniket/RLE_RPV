import os
import sqlite3
from contextlib import closing
from datetime import datetime

DB_PATH = "university_rle_rpv.db"
SCHEMA_FILE = "university_rle_rpv_schema.sql"
DUMP_FILE = "university_rle_rpv_dump.sql"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    faculty TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_name TEXT NOT NULL,
    program_code TEXT NOT NULL,
    faculty TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(exam_name, program_code)
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT NOT NULL UNIQUE,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    faculty TEXT NOT NULL,
    name TEXT NOT NULL,
    prn TEXT NOT NULL,
    seat_no TEXT NOT NULL,
    sex TEXT,
    sem1 REAL,
    sem2 REAL,
    sem3 REAL,
    sem4 REAL,
    sem5 REAL,
    sem6 REAL,
    cgpi REAL,
    gcgpi REAL,
    remark TEXT,
    result_status TEXT,
    updated_at TEXT,
    UNIQUE(session_id, exam_id, prn)
);
CREATE TABLE IF NOT EXISTS edit_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    faculty TEXT NOT NULL,
    submitted_by INTEGER NOT NULL,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    admin_comment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    faculty TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS final_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    final_state TEXT NOT NULL DEFAULT 'PENDING',
    final_comment TEXT,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_username TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    message TEXT,
    created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def export_dump(conn):
    with open(DUMP_FILE, "w", encoding="utf-8") as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")


def commit_db(conn):
    conn.commit()
    export_dump(conn)


def write_schema_file():
    if not os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
            f.write(SCHEMA_SQL.strip() + "\n")


def bootstrap_db(ccf_password_hash):
    write_schema_file()
    with closing(connect_db()) as conn:
        conn.executescript(SCHEMA_SQL)
        row = conn.execute("SELECT id FROM users WHERE username='BEAST'").fetchone()
        if row:
            conn.execute(
                "UPDATE users SET password_hash=?, role='CCF', is_active=1, updated_at=? WHERE username='BEAST'",
                (ccf_password_hash, now()),
            )
        else:
            conn.execute(
                "INSERT INTO users(username,password_hash,role,faculty,is_active,created_at) VALUES(?,?,?,?,?,?)",
                ("BEAST", ccf_password_hash, "CCF", None, 1, now()),
            )
        commit_db(conn)
