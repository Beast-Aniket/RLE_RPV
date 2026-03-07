import csv
import hashlib
import io
import os
import ast
import sqlite3
from contextlib import closing
from datetime import datetime

import pandas as pd
import streamlit as st
from dbfread import DBF

DB_PATH = "university_rle_rpv.db"
SCHEMA_FILE = "university_rle_rpv_schema.sql"
DUMP_FILE = "university_rle_rpv_dump.sql"

FACULTIES = [
    "Science & Technology",
    "Commerce & Management",
    "Interdisciplinary",
    "Humanities",
]
ROLES = ["CLERK", "ADMIN", "FINAL"]

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
    exam_name TEXT UNIQUE NOT NULL,
    faculty TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT NOT NULL,
    exam_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_name, exam_id)
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
    UNIQUE(session_id, prn)
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
    letter_text TEXT NOT NULL,
    final_state TEXT DEFAULT 'PENDING',
    final_comment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
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


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


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


def audit(conn, action, entity_type, entity_id=None, message=""):
    actor = st.session_state.get("username", "SYSTEM")
    conn.execute(
        "INSERT INTO audit_logs(actor_username, action, entity_type, entity_id, message, created_at) VALUES(?,?,?,?,?,?)",
        (actor, action, entity_type, entity_id, message, now()),
    )


def bootstrap():
    write_schema_file()
    with closing(connect_db()) as conn:
        conn.executescript(SCHEMA_SQL)
        ccf = conn.execute("SELECT id FROM users WHERE username='BEAST'").fetchone()
        if not ccf:
            conn.execute(
                "INSERT INTO users(username,password_hash,role,faculty,is_active,created_at) VALUES(?,?,?,?,?,?)",
                ("BEAST", hash_password("admin123"), "CCF", None, 1, now()),
            )
        else:
            conn.execute(
                "UPDATE users SET password_hash=?, role='CCF', is_active=1, updated_at=? WHERE username='BEAST'",
                (hash_password("admin123"), now()),
            )
        commit_db(conn)


def calc_cgpi(row):
    vals = [row.get(f"sem{i}") for i in range(1, 7)]
    vals = [float(v) for v in vals if v not in (None, "")]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def parse_float(v):
    if v in (None, ""):
        return None
    return float(v)


def normalize_upload(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        content = uploaded_file.getvalue().decode("utf-8")
        return list(csv.DictReader(io.StringIO(content)))
    if name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file).to_dict(orient="records")
    if name.endswith(".dbf"):
        tmp = f"tmp_{datetime.now().timestamp()}.dbf"
        with open(tmp, "wb") as f:
            f.write(uploaded_file.getbuffer())
        rows = [dict(r) for r in DBF(tmp)]
        os.remove(tmp)
        return rows
    raise ValueError("Unsupported file type")


def load_user(conn, username, password):
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=? AND is_active=1",
        (username, hash_password(password)),
    ).fetchone()
    return row


def login_view():
    st.title("University RLE-RPV Management System")
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login", use_container_width=True):
        with closing(connect_db()) as conn:
            user = load_user(conn, username, password)
            if user:
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = user["id"]
                st.session_state["username"] = user["username"]
                st.session_state["role"] = user["role"]
                st.session_state["faculty"] = user["faculty"]
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Invalid credentials")

    st.info("CCF Login: username = BEAST, password = admin123")


def ccf_user_management(conn):
    st.markdown("### User Management (Create / Modify / Delete)")
    tab1, tab2, tab3 = st.tabs(["Create User", "Modify User", "Delete/Disable User"])

    with tab1:
        u = st.text_input("New Username")
        p = st.text_input("New Password", type="password")
        r = st.selectbox("Role", ROLES)
        f = st.selectbox("Faculty", ["-- Not required --"] + FACULTIES)
        if st.button("Create User"):
            if not u or not p:
                st.warning("Username and password required")
            else:
                faculty = None if r == "FINAL" else (None if f.startswith("--") else f)
                try:
                    conn.execute(
                        "INSERT INTO users(username,password_hash,role,faculty,is_active,created_at) VALUES(?,?,?,?,?,?)",
                        (u, hash_password(p), r, faculty, 1, now()),
                    )
                    audit(conn, "CREATE_USER", "users", message=f"Created user {u}")
                    commit_db(conn)
                    st.success("User created")
                except sqlite3.IntegrityError:
                    st.error("Username already exists")

    users = conn.execute(
        "SELECT * FROM users WHERE username <> 'BEAST' ORDER BY role, faculty, username"
    ).fetchall()

    with tab2:
        if users:
            options = {f"{x['username']} ({x['role']})": x for x in users}
            selected = st.selectbox("Select user", list(options.keys()))
            user = options[selected]
            new_pwd = st.text_input("New password (leave blank to keep)", type="password")
            new_role = st.selectbox("New role", ROLES, index=ROLES.index(user["role"]))
            faculty_options = ["-- None --"] + FACULTIES
            current_fac_idx = 0 if not user["faculty"] else faculty_options.index(user["faculty"])
            new_faculty = st.selectbox("New faculty", faculty_options, index=current_fac_idx)
            active = st.checkbox("Active", value=bool(user["is_active"]))
            if st.button("Update User"):
                pwd_hash = user["password_hash"] if not new_pwd else hash_password(new_pwd)
                final_fac = None if new_role == "FINAL" else (None if new_faculty == "-- None --" else new_faculty)
                conn.execute(
                    "UPDATE users SET password_hash=?, role=?, faculty=?, is_active=?, updated_at=? WHERE id=?",
                    (pwd_hash, new_role, final_fac, int(active), now(), user["id"]),
                )
                audit(conn, "UPDATE_USER", "users", user["id"], f"Updated user {user['username']}")
                commit_db(conn)
                st.success("User updated")
                st.rerun()

    with tab3:
        if users:
            options = {f"{x['username']} ({x['role']})": x for x in users}
            selected = st.selectbox("Select user to disable", list(options.keys()), key="disable_user")
            user = options[selected]
            if st.button("Disable User"):
                conn.execute("UPDATE users SET is_active=0, updated_at=? WHERE id=?", (now(), user["id"]))
                audit(conn, "DISABLE_USER", "users", user["id"], f"Disabled user {user['username']}")
                commit_db(conn)
                st.success("User disabled")


def ccf_exam_session_upload(conn):
    st.markdown("### Exam, Session and Result Upload")

    exam_rows = conn.execute("SELECT * FROM exams ORDER BY exam_name").fetchall()
    exam_names = [r["exam_name"] for r in exam_rows]
    exam_choice = st.selectbox("Select existing exam or create new", exam_names + ["+ Create New Exam"])

    if exam_choice == "+ Create New Exam":
        new_exam = st.text_input("New Exam Name")
        exam_faculty = st.selectbox("Faculty for this exam", FACULTIES)
        if st.button("Create Exam"):
            if not new_exam.strip():
                st.warning("Exam name required")
            else:
                try:
                    conn.execute(
                        "INSERT INTO exams(exam_name,faculty,created_by,created_at) VALUES(?,?,?,?)",
                        (new_exam.strip(), exam_faculty, st.session_state["user_id"], now()),
                    )
                    audit(conn, "CREATE_EXAM", "exams", message=f"{new_exam.strip()} ({exam_faculty})")
                    commit_db(conn)
                    st.success("Exam created")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Exam already exists")
        return

    exam = next((r for r in exam_rows if r["exam_name"] == exam_choice), None)
    if not exam:
        return
    st.caption(f"Exam faculty mapping: {exam['faculty']}")

    session_name = st.text_input("Session Name (e.g., April 2025)")
    if st.button("Create Session"):
        if not session_name.strip():
            st.warning("Session name required")
        else:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_name,exam_id,created_by,created_at) VALUES(?,?,?,?)",
                (session_name.strip(), exam["id"], st.session_state["user_id"], now()),
            )
            audit(conn, "CREATE_SESSION", "sessions", message=f"{session_name} for {exam_choice}")
            commit_db(conn)
            st.success("Session created")

    sessions = conn.execute(
        "SELECT * FROM sessions WHERE exam_id=? ORDER BY id DESC", (exam["id"],)
    ).fetchall()
    if sessions:
        session_map = {f"{s['session_name']} (ID:{s['id']})": s for s in sessions}
        selected_session_label = st.selectbox("Select Session for Upload", list(session_map.keys()))
        selected_session = session_map[selected_session_label]

        uploaded = st.file_uploader("Upload CSV/XLSX/DBF", type=["csv", "xlsx", "dbf"])
        if st.button("Upload Result File"):
            if not uploaded:
                st.warning("Please upload a file")
            else:
                try:
                    rows = normalize_upload(uploaded)
                    inserted = 0
                    skipped = 0
                    for r in rows:
                        student = {
                            "name": r.get("name") or r.get("NAME"),
                            "prn": str(r.get("prn") or r.get("PRN") or "").strip(),
                            "seat_no": str(r.get("seat_no") or r.get("SEAT_NO") or "").strip(),
                            "sex": r.get("sex") or r.get("SEX"),
                            "sem1": parse_float(r.get("sem1") or r.get("SEM1")),
                            "sem2": parse_float(r.get("sem2") or r.get("SEM2")),
                            "sem3": parse_float(r.get("sem3") or r.get("SEM3")),
                            "sem4": parse_float(r.get("sem4") or r.get("SEM4")),
                            "sem5": parse_float(r.get("sem5") or r.get("SEM5")),
                            "sem6": parse_float(r.get("sem6") or r.get("SEM6")),
                            "gcgpi": parse_float(r.get("gcgpi") or r.get("GCGPI")),
                            "remark": r.get("remark") or r.get("REMARK"),
                            "result_status": r.get("result_status") or r.get("RESULT_STATUS"),
                        }
                        if not (student["name"] and student["prn"] and student["seat_no"]):
                            skipped += 1
                            continue
                        student["cgpi"] = calc_cgpi(student)
                        conn.execute(
                            """INSERT OR REPLACE INTO students
                            (id,session_id,exam_id,faculty,name,prn,seat_no,sex,sem1,sem2,sem3,sem4,sem5,sem6,cgpi,gcgpi,remark,result_status,updated_at)
                            VALUES(
                                (SELECT id FROM students WHERE session_id=? AND prn=?),
                                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                            )""",
                            (
                                selected_session["id"],
                                student["prn"],
                                selected_session["id"],
                                exam["id"],
                                exam["faculty"],
                                student["name"],
                                student["prn"],
                                student["seat_no"],
                                student["sex"],
                                student["sem1"],
                                student["sem2"],
                                student["sem3"],
                                student["sem4"],
                                student["sem5"],
                                student["sem6"],
                                student["cgpi"],
                                student["gcgpi"],
                                student["remark"],
                                student["result_status"],
                                now(),
                            ),
                        )
                        inserted += 1
                    audit(
                        conn,
                        "UPLOAD_RESULTS",
                        "students",
                        message=f"Exam={exam['exam_name']} Session={selected_session['session_name']} inserted={inserted} skipped={skipped}",
                    )
                    commit_db(conn)
                    st.success(f"Upload done. Inserted={inserted}, Skipped={skipped}")
                except Exception as e:
                    st.error(f"Upload failed: {e}")

    summary = conn.execute(
        """SELECT e.exam_name, e.faculty, s.session_name, COUNT(st.id) AS total_records
        FROM sessions s
        JOIN exams e ON e.id=s.exam_id
        LEFT JOIN students st ON st.session_id=s.id
        GROUP BY e.exam_name, e.faculty, s.session_name
        ORDER BY s.id DESC"""
    ).fetchall()
    if summary:
        st.markdown("### Upload Summary")
        st.dataframe(pd.DataFrame([dict(x) for x in summary]), use_container_width=True)


def clerk_page(conn):
    faculty = st.session_state.get("faculty")
    st.subheader(f"Clerk Dashboard - {faculty}")

    sessions = conn.execute(
        """SELECT s.id, s.session_name, e.exam_name, e.faculty
        FROM sessions s JOIN exams e ON e.id=s.exam_id
        WHERE e.faculty=? ORDER BY s.id DESC""",
        (faculty,),
    ).fetchall()
    if not sessions:
        st.info("No sessions available for your faculty")
        return

    session_map = {f"{x['session_name']} | {x['exam_name']}": x for x in sessions}
    selected = session_map[st.selectbox("Select Session", list(session_map.keys()))]

    q = st.text_input("Enter PRN or Seat Number")
    if q:
        student = conn.execute(
            "SELECT * FROM students WHERE session_id=? AND faculty=? AND (prn=? OR seat_no=?)",
            (selected["id"], faculty, q.strip(), q.strip()),
        ).fetchone()
        if student:
            st.success(f"Student: {student['name']} ({student['prn']})")
            cols = st.columns(6)
            sem_vals = {}
            for i in range(1, 7):
                sem_vals[f"sem{i}"] = cols[i - 1].text_input(f"Sem{i}", value="" if student[f"sem{i}"] is None else str(student[f"sem{i}"]))
            remark = st.text_input("Remark", value=student["remark"] or "")
            result_status = st.text_input("Result Status", value=student["result_status"] or "")
            mark_eligible = st.checkbox("For RPV, set ELIGIBLE and remove RPV remark")
            if st.button("Submit Request to Admin"):
                parsed = {k: parse_float(v) for k, v in sem_vals.items()}
                status = result_status.strip()
                rm = remark.strip()
                if mark_eligible and status.upper() == "RPV":
                    status = "ELIGIBLE"
                    rm = rm.replace("RPV", "").strip()
                payload = {
                    **parsed,
                    "remark": rm,
                    "result_status": status,
                    "cgpi": calc_cgpi(parsed),
                }
                req_type = "RPV" if result_status.strip().upper() == "RPV" else "RLE"
                conn.execute(
                    """INSERT INTO edit_requests(student_id,session_id,exam_id,faculty,submitted_by,request_type,status,payload_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        student["id"],
                        selected["id"],
                        student["exam_id"],
                        faculty,
                        st.session_state["user_id"],
                        req_type,
                        "SUBMITTED_BY_CLERK",
                        str(payload),
                        now(),
                        now(),
                    ),
                )
                audit(conn, "SUBMIT_REQUEST", "edit_requests", message=f"student_id={student['id']}")
                commit_db(conn)
                st.success("Request submitted")
        else:
            st.warning("Student not found")

    st.markdown("### My Requests")
    reqs = conn.execute(
        """SELECT er.id, er.request_type, er.status, er.admin_comment, er.created_at, st.name, st.prn
        FROM edit_requests er JOIN students st ON st.id=er.student_id
        WHERE er.submitted_by=? ORDER BY er.id DESC""",
        (st.session_state["user_id"],),
    ).fetchall()
    if reqs:
        st.dataframe(pd.DataFrame([dict(x) for x in reqs]), use_container_width=True)


def render_letter(student, payload_text):
    return (
        f"UNIVERSITY RESULT CORRECTION LETTER\n"
        f"Date: {now()}\n"
        f"Session: {student['session_name']}\n"
        f"Exam: {student['exam_name']}\n"
        f"Faculty: {student['faculty']}\n"
        f"Student: {student['name']} ({student['prn']})\n"
        f"Seat: {student['seat_no']}\n"
        f"Changes: {payload_text}\n"
        f"Approved by Faculty Admin."
    )


def admin_page(conn):
    faculty = st.session_state.get("faculty")
    st.subheader(f"Admin Dashboard - {faculty}")

    reqs = conn.execute(
        """SELECT er.*, st.name, st.prn, st.seat_no, s.session_name, e.exam_name
        FROM edit_requests er
        JOIN students st ON st.id=er.student_id
        JOIN sessions s ON s.id=er.session_id
        JOIN exams e ON e.id=er.exam_id
        WHERE er.faculty=?
        ORDER BY er.id DESC""",
        (faculty,),
    ).fetchall()
    if not reqs:
        st.info("No requests yet")
        return

    df = pd.DataFrame([dict(x) for x in reqs])
    st.dataframe(df[["id", "session_name", "exam_name", "name", "prn", "request_type", "status", "admin_comment", "created_at"]], use_container_width=True)

    req_map = {f"Request #{r['id']} | {r['name']} | {r['status']}": r for r in reqs}
    selected = req_map[st.selectbox("Select Request", list(req_map.keys()))]
    st.code(selected["payload_json"])
    comment = st.text_input("Admin comment")
    c1, c2, c3 = st.columns(3)

    if c1.button("Approve"):
        conn.execute(
            "UPDATE edit_requests SET status='ADMIN_APPROVED', admin_comment=?, updated_at=? WHERE id=?",
            (comment, now(), selected["id"]),
        )
        # minimal payload parser from str(dict)
        payload = ast.literal_eval(selected["payload_json"])
        conn.execute(
            """UPDATE students SET sem1=?,sem2=?,sem3=?,sem4=?,sem5=?,sem6=?,cgpi=?,remark=?,result_status=?,updated_at=? WHERE id=?""",
            (
                payload.get("sem1"), payload.get("sem2"), payload.get("sem3"), payload.get("sem4"), payload.get("sem5"), payload.get("sem6"),
                payload.get("cgpi"), payload.get("remark"), payload.get("result_status"), now(), selected["student_id"],
            ),
        )
        student = conn.execute(
            """SELECT st.*, s.session_name, e.exam_name
            FROM students st JOIN sessions s ON s.id=st.session_id JOIN exams e ON e.id=st.exam_id
            WHERE st.id=?""",
            (selected["student_id"],),
        ).fetchone()
        letter = render_letter(student, selected["payload_json"])
        conn.execute(
            "INSERT INTO letters(request_id,student_id,session_id,exam_id,faculty,letter_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (selected["id"], selected["student_id"], selected["session_id"], selected["exam_id"], faculty, letter, now(), now()),
        )
        audit(conn, "APPROVE_REQUEST", "edit_requests", selected["id"], f"Approved by {st.session_state['username']}")
        commit_db(conn)
        st.success("Approved and moved to letters")
        st.rerun()

    if c2.button("Reject"):
        conn.execute(
            "UPDATE edit_requests SET status='ADMIN_REJECTED', admin_comment=?, updated_at=? WHERE id=?",
            (comment, now(), selected["id"]),
        )
        audit(conn, "REJECT_REQUEST", "edit_requests", selected["id"], comment)
        commit_db(conn)
        st.warning("Request rejected")
        st.rerun()

    if c3.button("Suggest Edit"):
        conn.execute(
            "UPDATE edit_requests SET status='ADMIN_SUGGESTED_EDIT', admin_comment=?, updated_at=? WHERE id=?",
            (comment, now(), selected["id"]),
        )
        audit(conn, "SUGGEST_EDIT", "edit_requests", selected["id"], comment)
        commit_db(conn)
        st.info("Suggested edit sent")
        st.rerun()


def final_page(conn):
    st.subheader("Final Processing Dashboard")

    letters = conn.execute(
        """SELECT l.*, st.name, st.prn, s.session_name, e.exam_name
        FROM letters l
        JOIN students st ON st.id=l.student_id
        JOIN sessions s ON s.id=l.session_id
        JOIN exams e ON e.id=l.exam_id
        ORDER BY l.id DESC"""
    ).fetchall()
    if not letters:
        st.info("No approved letters yet")
        return

    df = pd.DataFrame([dict(x) for x in letters])
    st.dataframe(df[["id", "session_name", "exam_name", "name", "prn", "final_state", "created_at"]], use_container_width=True)

    summary = conn.execute(
        """SELECT date(created_at) AS date_key, session_id, COUNT(*) AS total,
        SUM(CASE WHEN final_state='DONE' THEN 1 ELSE 0 END) AS done_count
        FROM letters GROUP BY date(created_at), session_id ORDER BY date_key DESC"""
    ).fetchall()
    st.markdown("### Date-wise Pending")
    st.dataframe(pd.DataFrame([dict(x) for x in summary]), use_container_width=True)

    let_map = {f"Letter #{r['id']} | {r['name']} | {r['final_state']}": r for r in letters}
    selected = let_map[st.selectbox("Select Letter", list(let_map.keys()))]
    st.text_area("Letter Text", value=selected["letter_text"], height=220)

    state = st.selectbox("Final State", ["PENDING", "DONE", "QUERY"], index=["PENDING", "DONE", "QUERY"].index(selected["final_state"]))
    comment = st.text_input("Final comment / query")
    if st.button("Update Final State"):
        conn.execute(
            "UPDATE letters SET final_state=?, final_comment=?, updated_at=? WHERE id=?",
            (state, comment, now(), selected["id"]),
        )
        audit(conn, "FINAL_STATE_UPDATE", "letters", selected["id"], f"state={state}")
        commit_db(conn)
        st.success("Updated")
        st.rerun()

    st.download_button(
        "Download This Letter",
        selected["letter_text"],
        file_name=f"letter_{selected['id']}.txt",
        mime="text/plain",
    )


def ccf_dashboard(conn):
    st.subheader("CCF Dashboard")
    ccf_user_management(conn)
    st.divider()
    ccf_exam_session_upload(conn)

    st.divider()
    st.markdown("### System Audit (latest 50)")
    logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50").fetchall()
    if logs:
        st.dataframe(pd.DataFrame([dict(x) for x in logs]), use_container_width=True)
    if os.path.exists(DUMP_FILE):
        with open(DUMP_FILE, "rb") as f:
            st.download_button("Download SQL Dump", f.read(), file_name=DUMP_FILE)


def app_shell():
    st.set_page_config(page_title="University RLE-RPV", layout="wide")
    bootstrap()

    if not st.session_state.get("logged_in"):
        login_view()
        return

    with st.sidebar:
        st.write(f"**User:** {st.session_state.get('username')}")
        st.write(f"**Role:** {st.session_state.get('role')}")
        if st.session_state.get("faculty"):
            st.write(f"**Faculty:** {st.session_state.get('faculty')}")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

    with closing(connect_db()) as conn:
        role = st.session_state.get("role")
        if role == "CCF":
            ccf_dashboard(conn)
        elif role == "CLERK":
            clerk_page(conn)
        elif role == "ADMIN":
            admin_page(conn)
        elif role == "FINAL":
            final_page(conn)
        else:
            st.error("Invalid role configuration")


if __name__ == "__main__":
    app_shell()
