import csv
import io
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from functools import wraps
from zipfile import ZipFile

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    from dbfread import DBF
except Exception:  # pragma: no cover
    DBF = None


app = Flask(__name__)
app.secret_key = "change-this-secret-in-production"
DB_PATH = "rle_rpv.db"
SCHEMA_FILE = "rle_rpv_schema.sql"
DUMP_FILE = "rle_rpv_dump.sql"

FACULTIES = [
    "Science & Technology",
    "Commerce & Management",
    "Interdisciplinary",
    "Humanities",
]

STATUS_TABS = {
    "pending": ["SUBMITTED_BY_CLERK", "RESUBMITTED_BY_CLERK"],
    "approved": ["ADMIN_APPROVED"],
    "rejected": ["ADMIN_REJECTED"],
    "suggested": ["ADMIN_SUGGESTED_EDIT"],
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    faculty TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exam_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    start_date TEXT,
    end_date TEXT,
    created_at TEXT NOT NULL,
    created_by INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    faculty TEXT NOT NULL,
    name TEXT NOT NULL,
    prn TEXT NOT NULL,
    seat_no TEXT NOT NULL,
    sex TEXT,
    cgpi REAL,
    gcgpi REAL,
    sem1 REAL,
    sem2 REAL,
    sem3 REAL,
    sem4 REAL,
    sem5 REAL,
    sem6 REAL,
    remark TEXT,
    result_status TEXT,
    updated_at TEXT,
    UNIQUE(session_id, prn)
);

CREATE TABLE IF NOT EXISTS edit_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    clerk_id INTEGER NOT NULL,
    admin_id INTEGER,
    parent_request_id INTEGER,
    faculty TEXT NOT NULL,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    admin_comment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    session_name TEXT NOT NULL,
    faculty TEXT NOT NULL,
    letter_body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    final_state TEXT DEFAULT 'PENDING',
    final_comment TEXT,
    final_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def write_schema_file():
    if not os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
            f.write(SCHEMA_SQL.strip() + "\n")


def export_sql_dump(db=None):
    close_after = False
    if db is None:
        db = sqlite3.connect(DB_PATH)
        close_after = True
    with open(DUMP_FILE, "w", encoding="utf-8") as dump_file:
        for line in db.iterdump():
            dump_file.write(f"{line}\n")
    if close_after:
        db.close()


def db_commit(db):
    db.commit()
    export_sql_dump(db)


def log_action(db, action, entity_type, entity_id=None, payload=None):
    db.execute(
        """INSERT INTO audit_logs(actor_user_id, action, entity_type, entity_id, payload_json, created_at)
        VALUES(?,?,?,?,?,?)""",
        (
            session.get("user_id"),
            action,
            entity_type,
            entity_id,
            json.dumps(payload) if payload is not None else None,
            now(),
        ),
    )


def seed_users(db):
    default_users = [
        ("ccf", "ccf123", "ccf", None),
        ("clerk_snt", "clerk123", "clerk", FACULTIES[0]),
        ("admin_snt", "admin123", "admin", FACULTIES[0]),
        ("clerk_com", "clerk123", "clerk", FACULTIES[1]),
        ("admin_com", "admin123", "admin", FACULTIES[1]),
        ("clerk_inter", "clerk123", "clerk", FACULTIES[2]),
        ("admin_inter", "admin123", "admin", FACULTIES[2]),
        ("clerk_hum", "clerk123", "clerk", FACULTIES[3]),
        ("admin_hum", "admin123", "admin", FACULTIES[3]),
        ("final_member", "final123", "final", None),
    ]
    for username, password, role, faculty in default_users:
        exists = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO users(username,password_hash,role,faculty,created_at) VALUES(?,?,?,?,?)",
                (username, generate_password_hash(password), role, faculty, now()),
            )


def init_db():
    write_schema_file()
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.executescript(SCHEMA_SQL)
        seed_users(db)
        db.commit()
    export_sql_dump()


def login_required(role=None):
    def dec(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Unauthorized access.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return wrapped

    return dec


def parse_float(value):
    if value in (None, ""):
        return None
    return float(value)


def calc_cgpi(data):
    gp = [data.get(f"sem{i}") for i in range(1, 7)]
    clean = [float(v) for v in gp if v not in (None, "")]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 2)


def get_request_type(result_status):
    status = (result_status or "").upper().strip()
    if status == "RPV":
        return "RPV"
    return "RLE"


def rows_from_upload(file_storage):
    if not file_storage:
        raise ValueError("No file selected")
    filename = file_storage.filename.lower()
    if filename.endswith(".csv"):
        text = io.StringIO(file_storage.stream.read().decode("utf-8"))
        return list(csv.DictReader(text))
    if filename.endswith(".xlsx"):
        if not pd:
            raise ValueError("pandas/openpyxl not available")
        return pd.read_excel(file_storage).to_dict(orient="records")
    if filename.endswith(".dbf"):
        if not DBF:
            raise ValueError("dbfread not available")
        tmp = os.path.join("/tmp", f"upload_{datetime.now().timestamp()}.dbf")
        file_storage.save(tmp)
        rows = [dict(r) for r in DBF(tmp)]
        os.remove(tmp)
        return rows
    raise ValueError("Unsupported file type. Use .csv, .xlsx, or .dbf")


@app.route("/")
def home():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.update(
                {
                    "user_id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                    "faculty": user["faculty"],
                }
            )
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    role = session.get("role")
    if role == "ccf":
        return redirect(url_for("ccf_dashboard"))
    if role == "clerk":
        return redirect(url_for("clerk_dashboard"))
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("final_dashboard"))


@app.route("/ccf", methods=["GET", "POST"])
@login_required("ccf")
def ccf_dashboard():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_session":
            name = request.form.get("session_name", "").strip()
            start_date = request.form.get("start_date") or None
            end_date = request.form.get("end_date") or None
            if not name:
                flash("Session name is required.", "warning")
            else:
                db.execute(
                    "INSERT OR IGNORE INTO exam_sessions(name,start_date,end_date,created_at,created_by) VALUES(?,?,?,?,?)",
                    (name, start_date, end_date, now(), session["user_id"]),
                )
                log_action(db, "CREATE_SESSION", "exam_session", payload={"name": name})
                db_commit(db)
                flash("Session created successfully.", "success")

        elif action == "upload":
            session_id = request.form.get("session_id")
            faculty = request.form.get("faculty")
            uploaded = request.files.get("file")
            try:
                rows = rows_from_upload(uploaded)
                inserted = 0
                skipped = 0
                for row in rows:
                    record = {
                        "name": row.get("name") or row.get("NAME"),
                        "prn": str(row.get("prn") or row.get("PRN") or "").strip(),
                        "seat_no": str(row.get("seat_no") or row.get("SEAT_NO") or "").strip(),
                        "sex": row.get("sex") or row.get("SEX"),
                        "sem1": parse_float(row.get("sem1") or row.get("SEM1")),
                        "sem2": parse_float(row.get("sem2") or row.get("SEM2")),
                        "sem3": parse_float(row.get("sem3") or row.get("SEM3")),
                        "sem4": parse_float(row.get("sem4") or row.get("SEM4")),
                        "sem5": parse_float(row.get("sem5") or row.get("SEM5")),
                        "sem6": parse_float(row.get("sem6") or row.get("SEM6")),
                        "gcgpi": parse_float(row.get("gcgpi") or row.get("GCGPI")),
                        "remark": row.get("remark") or row.get("REMARK"),
                        "result_status": row.get("result_status") or row.get("RESULT_STATUS"),
                    }
                    if not (record["name"] and record["prn"] and record["seat_no"]):
                        skipped += 1
                        continue

                    record["cgpi"] = calc_cgpi(record)
                    db.execute(
                        """INSERT OR REPLACE INTO students
                        (id, session_id, faculty, name, prn, seat_no, sex, cgpi, gcgpi, sem1, sem2, sem3, sem4, sem5, sem6, remark, result_status, updated_at)
                        VALUES(
                            (SELECT id FROM students WHERE session_id=? AND prn=?),
                            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                        )
                        """,
                        (
                            session_id,
                            record["prn"],
                            session_id,
                            faculty,
                            record["name"],
                            record["prn"],
                            record["seat_no"],
                            record["sex"],
                            record["cgpi"],
                            record["gcgpi"],
                            record["sem1"],
                            record["sem2"],
                            record["sem3"],
                            record["sem4"],
                            record["sem5"],
                            record["sem6"],
                            record["remark"],
                            record["result_status"],
                            now(),
                        ),
                    )
                    inserted += 1

                log_action(
                    db,
                    "UPLOAD_SESSION_DATA",
                    "students",
                    payload={"session_id": session_id, "faculty": faculty, "inserted": inserted, "skipped": skipped},
                )
                db_commit(db)
                flash(f"Upload successful: inserted {inserted}, skipped {skipped} rows.", "success")
            except Exception as exc:
                flash(f"Upload failed: {exc}", "danger")

    sessions = db.execute("SELECT * FROM exam_sessions ORDER BY id DESC").fetchall()
    upload_summary = db.execute(
        """SELECT es.name AS session_name, st.faculty, COUNT(*) AS total
        FROM students st
        JOIN exam_sessions es ON es.id = st.session_id
        GROUP BY es.name, st.faculty
        ORDER BY es.id DESC, st.faculty"""
    ).fetchall()
    recent_logs = db.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return render_template(
        "ccf_dashboard.html",
        sessions=sessions,
        faculties=FACULTIES,
        upload_summary=upload_summary,
        recent_logs=recent_logs,
    )


@app.route("/clerk", methods=["GET", "POST"])
@login_required("clerk")
def clerk_dashboard():
    db = get_db()
    faculty = session["faculty"]

    selected_session = request.args.get("session_id", "")
    search = request.args.get("search", "").strip()
    tab = request.args.get("tab", "pending")
    if tab not in STATUS_TABS:
        tab = "pending"

    if request.method == "POST":
        student_id = request.form.get("student_id")
        parent_request_id = request.form.get("parent_request_id") or None

        sem_data = {f"sem{i}": parse_float(request.form.get(f"sem{i}")) for i in range(1, 7)}
        result_status = request.form.get("result_status", "").strip()
        remark = request.form.get("remark", "").strip()
        mark_eligible = request.form.get("mark_eligible") == "on"

        if mark_eligible and result_status.upper() == "RPV":
            result_status = "ELIGIBLE"
            remark = remark.replace("RPV", "").strip()

        payload = {
            **sem_data,
            "remark": remark,
            "result_status": result_status,
            "cgpi": calc_cgpi(sem_data),
        }

        request_type = get_request_type(result_status)
        status = "RESUBMITTED_BY_CLERK" if parent_request_id else "SUBMITTED_BY_CLERK"

        db.execute(
            """INSERT INTO edit_requests(student_id, clerk_id, admin_id, parent_request_id, faculty, request_type, status, payload_json, admin_comment, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                student_id,
                session["user_id"],
                None,
                parent_request_id,
                faculty,
                request_type,
                status,
                json.dumps(payload),
                None,
                now(),
                now(),
            ),
        )
        log_action(
            db,
            "SUBMIT_EDIT_REQUEST",
            "edit_request",
            payload={"student_id": student_id, "type": request_type, "status": status},
        )
        db_commit(db)
        flash("Request submitted to faculty admin.", "success")
        return redirect(url_for("clerk_dashboard", session_id=selected_session, search=search, tab="pending"))

    sessions = db.execute("SELECT * FROM exam_sessions ORDER BY id DESC").fetchall()

    student = None
    if selected_session and search:
        student = db.execute(
            """SELECT * FROM students
            WHERE session_id=? AND faculty=? AND (prn=? OR seat_no=?)""",
            (selected_session, faculty, search, search),
        ).fetchone()

    request_rows = db.execute(
        """SELECT er.*, st.name, st.prn, st.seat_no, es.name AS session_name
        FROM edit_requests er
        JOIN students st ON st.id = er.student_id
        JOIN exam_sessions es ON es.id = st.session_id
        WHERE er.clerk_id=?
        ORDER BY er.id DESC""",
        (session["user_id"],),
    ).fetchall()

    tab_rows = [row for row in request_rows if row["status"] in STATUS_TABS[tab]]
    tab_counts = {k: sum(1 for r in request_rows if r["status"] in v) for k, v in STATUS_TABS.items()}

    return render_template(
        "clerk_dashboard.html",
        sessions=sessions,
        selected_session=selected_session,
        search=search,
        student=student,
        tab=tab,
        tab_rows=tab_rows,
        tab_counts=tab_counts,
    )


@app.route("/admin", methods=["GET", "POST"])
@login_required("admin")
def admin_dashboard():
    db = get_db()
    faculty = session["faculty"]
    filter_status = request.args.get("status", "pending")

    if request.method == "POST":
        request_id = request.form.get("request_id")
        decision = request.form.get("decision")
        comment = request.form.get("comment", "").strip()

        req_row = db.execute("SELECT * FROM edit_requests WHERE id=? AND faculty=?", (request_id, faculty)).fetchone()
        if not req_row:
            flash("Request not found for your faculty.", "danger")
            return redirect(url_for("admin_dashboard"))

        status_map = {
            "approve": "ADMIN_APPROVED",
            "reject": "ADMIN_REJECTED",
            "suggest": "ADMIN_SUGGESTED_EDIT",
        }
        new_status = status_map.get(decision)
        if not new_status:
            flash("Invalid action.", "warning")
            return redirect(url_for("admin_dashboard"))

        if new_status in ("ADMIN_REJECTED", "ADMIN_SUGGESTED_EDIT") and not comment:
            flash("Comment is required for reject/suggest edit.", "warning")
            return redirect(url_for("admin_dashboard", status=filter_status))

        db.execute(
            "UPDATE edit_requests SET status=?, admin_id=?, admin_comment=?, updated_at=? WHERE id=?",
            (new_status, session["user_id"], comment or None, now(), request_id),
        )

        payload = json.loads(req_row["payload_json"])
        if new_status == "ADMIN_APPROVED":
            db.execute(
                """UPDATE students SET
                sem1=?, sem2=?, sem3=?, sem4=?, sem5=?, sem6=?,
                cgpi=?, remark=?, result_status=?, updated_at=?
                WHERE id=?""",
                (
                    payload.get("sem1"),
                    payload.get("sem2"),
                    payload.get("sem3"),
                    payload.get("sem4"),
                    payload.get("sem5"),
                    payload.get("sem6"),
                    payload.get("cgpi"),
                    payload.get("remark"),
                    payload.get("result_status"),
                    now(),
                    req_row["student_id"],
                ),
            )
            student = db.execute(
                """SELECT st.*, es.name AS session_name
                FROM students st JOIN exam_sessions es ON es.id=st.session_id
                WHERE st.id=?""",
                (req_row["student_id"],),
            ).fetchone()
            letter_body = render_letter(student, payload, comment)
            db.execute(
                """INSERT INTO letters(request_id, student_id, session_name, faculty, letter_body, created_at)
                VALUES(?,?,?,?,?,?)""",
                (request_id, req_row["student_id"], student["session_name"], faculty, letter_body, now()),
            )

        log_action(
            db,
            "ADMIN_DECISION",
            "edit_request",
            entity_id=int(request_id),
            payload={"decision": new_status, "comment": comment},
        )
        db_commit(db)
        flash(f"Request moved to {new_status}.", "success")

    status_map_view = {
        "pending": ["SUBMITTED_BY_CLERK", "RESUBMITTED_BY_CLERK"],
        "approved": ["ADMIN_APPROVED"],
        "rejected": ["ADMIN_REJECTED"],
        "suggested": ["ADMIN_SUGGESTED_EDIT"],
    }
    if filter_status not in status_map_view:
        filter_status = "pending"

    rows = db.execute(
        """SELECT er.*, st.name, st.prn, st.seat_no, st.result_status, st.cgpi, es.name AS session_name
        FROM edit_requests er
        JOIN students st ON st.id = er.student_id
        JOIN exam_sessions es ON es.id = st.session_id
        WHERE er.faculty=?
        ORDER BY er.id DESC""",
        (faculty,),
    ).fetchall()
    filtered = [r for r in rows if r["status"] in status_map_view[filter_status]]
    counts = {k: sum(1 for r in rows if r["status"] in vals) for k, vals in status_map_view.items()}
    return render_template("admin_dashboard.html", rows=filtered, counts=counts, filter_status=filter_status)


def render_letter(student, payload, admin_comment):
    date_line = now()
    return (
        f"UNIVERSITY RESULT CORRECTION LETTER\n"
        f"Date: {date_line}\n"
        f"---------------------------------------\n"
        f"Session      : {student['session_name']}\n"
        f"Faculty      : {student['faculty']}\n"
        f"Student Name : {student['name']}\n"
        f"PRN          : {student['prn']}\n"
        f"Seat No      : {student['seat_no']}\n"
        f"Result Status: {payload.get('result_status')}\n"
        f"CGPI         : {payload.get('cgpi')}\n"
        f"Remark       : {payload.get('remark')}\n"
        f"Admin Note   : {admin_comment or 'Approved as per faculty verification'}\n"
        f"---------------------------------------\n"
        f"This letter is system generated for final marksheet processing.\n"
    )


@app.route("/final", methods=["GET", "POST"])
@login_required("final")
def final_dashboard():
    db = get_db()
    session_filter = request.args.get("session_name", "")
    state_filter = request.args.get("state", "")

    if request.method == "POST":
        letter_id = request.form.get("letter_id")
        final_state = request.form.get("final_state")
        final_comment = request.form.get("final_comment", "").strip()
        db.execute(
            "UPDATE letters SET final_state=?, final_comment=?, final_updated_at=? WHERE id=?",
            (final_state, final_comment or None, now(), letter_id),
        )
        log_action(
            db,
            "FINAL_STATUS_UPDATE",
            "letter",
            entity_id=int(letter_id),
            payload={"state": final_state, "comment": final_comment},
        )
        db_commit(db)
        flash("Final status updated.", "success")

    query = """SELECT l.*, st.name, st.prn, st.seat_no, st.result_status, st.cgpi
    FROM letters l
    JOIN students st ON st.id=l.student_id
    WHERE 1=1"""
    params = []
    if session_filter:
        query += " AND l.session_name=?"
        params.append(session_filter)
    if state_filter:
        query += " AND l.final_state=?"
        params.append(state_filter)
    query += " ORDER BY l.id DESC"

    rows = db.execute(query, params).fetchall()
    grouped = db.execute(
        """SELECT date(created_at) AS work_date, session_name, COUNT(*) AS total,
        SUM(CASE WHEN final_state='DONE' THEN 1 ELSE 0 END) AS done_count,
        SUM(CASE WHEN final_state='QUERY' THEN 1 ELSE 0 END) AS query_count
        FROM letters
        GROUP BY date(created_at), session_name
        ORDER BY work_date DESC, session_name"""
    ).fetchall()
    sessions = db.execute("SELECT DISTINCT session_name FROM letters ORDER BY session_name DESC").fetchall()

    return render_template(
        "final_dashboard.html",
        rows=rows,
        grouped=grouped,
        sessions=sessions,
        session_filter=session_filter,
        state_filter=state_filter,
    )


@app.route("/download/letter/<int:letter_id>")
@login_required("final")
def download_letter(letter_id):
    db = get_db()
    letter = db.execute("SELECT * FROM letters WHERE id=?", (letter_id,)).fetchone()
    if not letter:
        return "Letter not found", 404
    payload = io.BytesIO(letter["letter_body"].encode("utf-8"))
    return send_file(payload, as_attachment=True, download_name=f"letter_{letter_id}.txt", mimetype="text/plain")


@app.route("/download/letters_zip")
@login_required("final")
def download_letters_zip():
    db = get_db()
    ids = request.args.get("ids", "")
    if not ids:
        return redirect(url_for("final_dashboard"))

    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not id_list:
        return redirect(url_for("final_dashboard"))

    placeholders = ",".join(["?"] * len(id_list))
    letters = db.execute(
        f"SELECT id, letter_body FROM letters WHERE id IN ({placeholders})",
        id_list,
    ).fetchall()

    memory = io.BytesIO()
    with ZipFile(memory, "w") as zf:
        for letter in letters:
            zf.writestr(f"letter_{letter['id']}.txt", letter["letter_body"])
    memory.seek(0)
    return send_file(memory, as_attachment=True, download_name="letters_bundle.zip", mimetype="application/zip")


@app.route("/download/day_report")
@login_required("final")
def download_day_report():
    day = request.args.get("day")
    if not day:
        return redirect(url_for("final_dashboard"))
    db = get_db()
    rows = db.execute(
        """SELECT l.id, l.session_name, l.faculty, st.name, st.prn, st.seat_no, st.cgpi,
        st.result_status, l.final_state, l.final_comment
        FROM letters l
        JOIN students st ON st.id=l.student_id
        WHERE date(l.created_at)=?""",
        (day,),
    ).fetchall()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "LetterID",
            "Session",
            "Faculty",
            "Name",
            "PRN",
            "SeatNo",
            "CGPI",
            "ResultStatus",
            "FinalState",
            "FinalComment",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["session_name"],
                r["faculty"],
                r["name"],
                r["prn"],
                r["seat_no"],
                r["cgpi"],
                r["result_status"],
                r["final_state"],
                r["final_comment"],
            ]
        )
    payload = io.BytesIO(out.getvalue().encode("utf-8"))
    return send_file(payload, as_attachment=True, download_name=f"day_report_{day}.csv", mimetype="text/csv")


@app.route("/download/sql_dump")
@login_required("ccf")
def download_sql_dump():
    export_sql_dump(get_db())
    return send_file(DUMP_FILE, as_attachment=True)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
