import csv
import io
import json
import os
from zipfile import ZipFile

import pandas as pd
import streamlit as st
from dbfread import DBF

from db import commit_db, now
from import_config import COLUMN_ALIASES

FACULTIES = ["Science & Technology", "Commerce & Management", "Interdisciplinary", "Humanities"]
ROLES = ["CLERK", "ADMIN", "FINAL"]


def audit(conn, action, entity_type, entity_id=None, message=""):
    conn.execute(
        "INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,message,created_at) VALUES(?,?,?,?,?,?)",
        (st.session_state.get("username"), action, entity_type, entity_id, message, now()),
    )


def parse_float(v):
    if v in (None, ""):
        return None
    return float(v)


def calc_cgpi(row):
    vals = [row.get(f"sem{i}") for i in range(1, 7)]
    vals = [float(v) for v in vals if v not in (None, "")]
    return round(sum(vals) / len(vals), 2) if vals else None


def get_col(rec, key):
    for alias in COLUMN_ALIASES[key]:
        if alias in rec and rec.get(alias) not in (None, ""):
            return rec.get(alias)
    return None


def normalize_upload(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return list(csv.DictReader(io.StringIO(uploaded_file.getvalue().decode("utf-8"))))
    if name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file).to_dict(orient="records")
    if name.endswith(".dbf"):
        tmp = f"tmp_{now().replace(' ', '_').replace(':','')}.dbf"
        with open(tmp, "wb") as f:
            f.write(uploaded_file.getbuffer())
        rows = [dict(x) for x in DBF(tmp)]
        os.remove(tmp)
        return rows
    raise ValueError("Unsupported file")


def user_management_tab(conn):
    st.markdown("### User Management")
    c1, c2, c3 = st.tabs(["Create", "Edit", "Delete/Disable"])

    with c1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        r = st.selectbox("Role", ROLES)
        f = st.selectbox("Faculty", ["--None--"] + FACULTIES)
        if st.button("Create User"):
            if not u or not p:
                st.warning("Username/password required")
            else:
                from auth import hash_password

                faculty = None if r == "FINAL" else (None if f == "--None--" else f)
                conn.execute(
                    "INSERT INTO users(username,password_hash,role,faculty,is_active,created_at) VALUES(?,?,?,?,?,?)",
                    (u, hash_password(p), r, faculty, 1, now()),
                )
                audit(conn, "CREATE_USER", "users", message=f"user={u}")
                commit_db(conn)
                st.success("User created")

    rows = conn.execute("SELECT * FROM users WHERE username<>'BEAST' ORDER BY role,username").fetchall()
    users = {f"{x['username']} ({x['role']})": x for x in rows}

    with c2:
        if users:
            k = st.selectbox("Select user", list(users.keys()))
            u = users[k]
            new_role = st.selectbox("Role", ROLES, index=ROLES.index(u["role"]))
            new_fac = st.selectbox("Faculty", ["--None--"] + FACULTIES, index=0 if not u["faculty"] else (1 + FACULTIES.index(u["faculty"])))
            new_pw = st.text_input("New password (optional)", type="password")
            active = st.checkbox("Active", value=bool(u["is_active"]))
            if st.button("Update User"):
                from auth import hash_password

                pw_hash = u["password_hash"] if not new_pw else hash_password(new_pw)
                final_fac = None if new_role == "FINAL" else (None if new_fac == "--None--" else new_fac)
                conn.execute("UPDATE users SET password_hash=?,role=?,faculty=?,is_active=?,updated_at=? WHERE id=?", (pw_hash, new_role, final_fac, int(active), now(), u["id"]))
                audit(conn, "UPDATE_USER", "users", u["id"], f"user={u['username']}")
                commit_db(conn)
                st.success("Updated")

    with c3:
        if users:
            k = st.selectbox("Select user", list(users.keys()), key="del_user")
            u = users[k]
            if st.button("Disable User"):
                conn.execute("UPDATE users SET is_active=0,updated_at=? WHERE id=?", (now(), u["id"]))
                audit(conn, "DISABLE_USER", "users", u["id"], f"user={u['username']}")
                commit_db(conn)
                st.success("Disabled")


def exam_session_upload_tab(conn):
    st.markdown("### Create Session")
    session_name = st.text_input("Session Name")
    if st.button("Create Session"):
        if session_name.strip():
            conn.execute("INSERT OR IGNORE INTO sessions(session_name,created_by,created_at) VALUES(?,?,?)", (session_name.strip(), st.session_state["user_id"], now()))
            audit(conn, "CREATE_SESSION", "sessions", message=session_name.strip())
            commit_db(conn)
            st.success("Session created")

    st.markdown("### Upload Exam Data")
    sessions = conn.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()
    if not sessions:
        st.info("Create session first")
        return

    session_map = {s["session_name"]: s for s in sessions}
    selected_session_name = st.selectbox("Select Session", list(session_map.keys()))
    selected_session = session_map[selected_session_name]

    faculty = st.selectbox("Faculty", FACULTIES)
    exams = conn.execute("SELECT * FROM exams WHERE faculty=? ORDER BY exam_name", (faculty,)).fetchall()
    exam_labels = [f"{e['exam_name']} ({e['program_code']})" for e in exams] + ["+ Create New Exam"]
    pick = st.selectbox("Exam Name + Program Code", exam_labels)

    exam_id = None
    if pick == "+ Create New Exam":
        ename = st.text_input("New Exam Name")
        pcode = st.text_input("Program Code")
        if st.button("Create Exam"):
            conn.execute("INSERT INTO exams(exam_name,program_code,faculty,created_by,created_at) VALUES(?,?,?,?,?)", (ename.strip(), pcode.strip(), faculty, st.session_state["user_id"], now()))
            audit(conn, "CREATE_EXAM", "exams", message=f"{ename} {pcode}")
            commit_db(conn)
            st.success("Exam created")
            st.rerun()
    else:
        exam_id = exams[exam_labels.index(pick)]["id"]

    uploaded = st.file_uploader("Upload file", type=["csv", "xlsx", "dbf"])
    if st.button("Upload Data"):
        if not exam_id:
            st.warning("Select/create exam first")
            return
        if not uploaded:
            st.warning("Upload file first")
            return
        rows = normalize_upload(uploaded)
        ins, skip = 0, 0
        for r in rows:
            st_rec = {
                "name": get_col(r, "name"),
                "prn": str(get_col(r, "prn") or "").strip(),
                "seat_no": str(get_col(r, "seat_no") or "").strip(),
                "sex": get_col(r, "sex"),
                "sem1": parse_float(get_col(r, "sem1")),
                "sem2": parse_float(get_col(r, "sem2")),
                "sem3": parse_float(get_col(r, "sem3")),
                "sem4": parse_float(get_col(r, "sem4")),
                "sem5": parse_float(get_col(r, "sem5")),
                "sem6": parse_float(get_col(r, "sem6")),
                "gcgpi": parse_float(get_col(r, "gcgpi")),
                "remark": get_col(r, "remark"),
                "result_status": get_col(r, "result_status"),
            }
            if not (st_rec["name"] and st_rec["prn"] and st_rec["seat_no"]):
                skip += 1
                continue
            st_rec["cgpi"] = calc_cgpi(st_rec)
            conn.execute(
                """INSERT OR REPLACE INTO students(id,session_id,exam_id,faculty,name,prn,seat_no,sex,sem1,sem2,sem3,sem4,sem5,sem6,cgpi,gcgpi,remark,result_status,updated_at)
                VALUES((SELECT id FROM students WHERE session_id=? AND exam_id=? AND prn=?),?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    selected_session["id"], exam_id, st_rec["prn"],
                    selected_session["id"], exam_id, faculty, st_rec["name"], st_rec["prn"], st_rec["seat_no"], st_rec["sex"],
                    st_rec["sem1"], st_rec["sem2"], st_rec["sem3"], st_rec["sem4"], st_rec["sem5"], st_rec["sem6"],
                    st_rec["cgpi"], st_rec["gcgpi"], st_rec["remark"], st_rec["result_status"], now(),
                ),
            )
            ins += 1
        audit(conn, "UPLOAD_STUDENTS", "students", message=f"inserted={ins} skipped={skip}")
        commit_db(conn)
        st.success(f"Uploaded. Inserted={ins}, Skipped={skip}")


def download_audit(conn):
    st.markdown("### Audit Log Download")
    logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC").fetchall()
    if not logs:
        st.info("No logs")
        return
    df = pd.DataFrame([dict(x) for x in logs])
    st.dataframe(df, use_container_width=True)
    st.download_button("Download Audit CSV", df.to_csv(index=False).encode("utf-8"), file_name="audit_logs.csv", mime="text/csv")


def render_ccf_page(conn):
    st.subheader("CCF Dashboard")
    t1, t2, t3 = st.tabs(["User Management", "Session/Exam Upload", "Audit"])
    with t1:
        user_management_tab(conn)
    with t2:
        exam_session_upload_tab(conn)
    with t3:
        download_audit(conn)
