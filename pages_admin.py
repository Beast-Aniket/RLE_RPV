import io
import json
import os
from datetime import datetime, timedelta
from zipfile import ZipFile

import pandas as pd
import streamlit as st

from db import commit_db, now
from pdf_generator import generate_letter_pdf


def audit(conn, action, entity_type, entity_id=None, message=""):
    conn.execute(
        "INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,message,created_at) VALUES(?,?,?,?,?,?)",
        (st.session_state.get("username"), action, entity_type, entity_id, message, now()),
    )


def filter_requests_df(df, date_from, date_to, session_name, exam_label, prn, seat, only_pending):
    out = df.copy()
    if date_from:
        out = out[out["created_at"].str[:10] >= str(date_from)]
    if date_to:
        out = out[out["created_at"].str[:10] <= str(date_to)]
    if session_name != "All":
        out = out[out["session_name"] == session_name]
    if exam_label != "All":
        out = out[out["exam_label"] == exam_label]
    if prn:
        out = out[out["prn"].str.contains(prn, case=False, na=False)]
    if seat:
        out = out[out["seat_no"].str.contains(seat, case=False, na=False)]
    if only_pending:
        out = out[out["status"] == "SUBMITTED_BY_CLERK"]
    return out


def download_zip_from_paths(file_paths):
    mem = io.BytesIO()
    with ZipFile(mem, "w") as zf:
        for p in file_paths:
            if os.path.exists(p):
                zf.write(p, arcname=os.path.basename(p))
    mem.seek(0)
    return mem.getvalue()


def render_admin_page(conn):
    faculty = st.session_state.get("faculty")
    st.subheader(f"Admin Dashboard - {faculty}")

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    c1, c2 = st.columns(2)
    if c1.button("Today's Report"):
        st.session_state["admin_date_from"] = today
        st.session_state["admin_date_to"] = today
    if c2.button("Yesterday's Report"):
        st.session_state["admin_date_from"] = yesterday
        st.session_state["admin_date_to"] = yesterday

    reqs = conn.execute(
        """SELECT er.*, st.name, st.prn, st.seat_no, s.session_name, e.exam_name, e.program_code
        FROM edit_requests er
        JOIN students st ON st.id=er.student_id
        JOIN sessions s ON s.id=er.session_id
        JOIN exams e ON e.id=er.exam_id
        WHERE er.faculty=? ORDER BY er.id DESC""",
        (faculty,),
    ).fetchall()
    if not reqs:
        st.info("No requests")
        return

    df = pd.DataFrame([dict(x) for x in reqs])
    df["exam_label"] = df["exam_name"] + " (" + df["program_code"] + ")"

    st.markdown("### Filters")
    f1, f2, f3, f4 = st.columns(4)
    date_from = f1.date_input("From", value=datetime.strptime(st.session_state.get("admin_date_from", today), "%Y-%m-%d").date())
    date_to = f2.date_input("To", value=datetime.strptime(st.session_state.get("admin_date_to", today), "%Y-%m-%d").date())
    session_name = f3.selectbox("Session", ["All"] + sorted(df["session_name"].unique().tolist()))
    exam_label = f4.selectbox("Exam", ["All"] + sorted(df["exam_label"].unique().tolist()))
    g1, g2, g3 = st.columns(3)
    prn = g1.text_input("PRN")
    seat = g2.text_input("Seat No")
    only_pending = g3.checkbox("Only pending", value=True)

    filtered = filter_requests_df(df, date_from, date_to, session_name, exam_label, prn, seat, only_pending)
    st.dataframe(filtered[["id", "session_name", "exam_label", "name", "prn", "seat_no", "request_type", "status", "created_at", "admin_comment"]], use_container_width=True)

    if filtered.empty:
        return

    select_map = {f"#{r['id']} | {r['name']} | {r['status']}": r for _, r in filtered.iterrows()}
    chosen = select_map[st.selectbox("Select Request", list(select_map.keys()))]
    payload = json.loads(chosen["payload_json"])
    st.json(payload)
    comment = st.text_input("Admin Comment")
    a1, a2, a3 = st.columns(3)

    if a1.button("Approve"):
        conn.execute("UPDATE edit_requests SET status='ADMIN_APPROVED',admin_comment=?,updated_at=? WHERE id=?", (comment, now(), int(chosen["id"])))
        conn.execute(
            """UPDATE students SET sem1=?,sem2=?,sem3=?,sem4=?,sem5=?,sem6=?,cgpi=?,remark=?,result_status=?,updated_at=? WHERE id=?""",
            (
                payload.get("sem1"), payload.get("sem2"), payload.get("sem3"), payload.get("sem4"), payload.get("sem5"), payload.get("sem6"),
                payload.get("cgpi"), payload.get("remark"), payload.get("result_status"), now(), int(chosen["student_id"]),
            ),
        )
        student = conn.execute(
            "SELECT st.*, s.session_name, e.exam_name, e.program_code FROM students st JOIN sessions s ON s.id=st.session_id JOIN exams e ON e.id=st.exam_id WHERE st.id=?",
            (int(chosen["student_id"]),),
        ).fetchone()
        path = generate_letter_pdf(student, chosen, payload, comment)
        conn.execute(
            "INSERT INTO letters(request_id,student_id,session_id,exam_id,faculty,pdf_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (int(chosen["id"]), int(chosen["student_id"]), int(chosen["session_id"]), int(chosen["exam_id"]), faculty, path, now(), now()),
        )
        conn.execute(
            "INSERT OR REPLACE INTO final_actions(request_id,final_state,final_comment,updated_by,updated_at) VALUES(?,?,?,?,?)",
            (int(chosen["id"]), "PENDING", None, st.session_state["user_id"], now()),
        )
        audit(conn, "ADMIN_APPROVE", "edit_requests", int(chosen["id"]), f"pdf={path}")
        commit_db(conn)
        st.success("Approved and PDF generated")
        st.rerun()

    if a2.button("Reject"):
        conn.execute("UPDATE edit_requests SET status='ADMIN_REJECTED',admin_comment=?,updated_at=? WHERE id=?", (comment, now(), int(chosen["id"])))
        audit(conn, "ADMIN_REJECT", "edit_requests", int(chosen["id"]), comment)
        commit_db(conn)
        st.warning("Rejected")
        st.rerun()

    if a3.button("Suggest Edit"):
        conn.execute("UPDATE edit_requests SET status='ADMIN_SUGGESTED_EDIT',admin_comment=?,updated_at=? WHERE id=?", (comment, now(), int(chosen["id"])))
        audit(conn, "ADMIN_SUGGEST", "edit_requests", int(chosen["id"]), comment)
        commit_db(conn)
        st.info("Suggested")
        st.rerun()

    st.markdown("### PDF Downloads")
    pdf_rows = conn.execute(
        """SELECT l.pdf_path, s.session_name, e.exam_name, e.program_code, date(l.created_at) as created_day
        FROM letters l JOIN sessions s ON s.id=l.session_id JOIN exams e ON e.id=l.exam_id
        WHERE l.faculty=?""",
        (faculty,),
    ).fetchall()
    if pdf_rows:
        p_df = pd.DataFrame([dict(x) for x in pdf_rows])
        p_df["exam_label"] = p_df["exam_name"] + " (" + p_df["program_code"] + ")"
        s_f = st.selectbox("PDF Filter Session", ["All"] + sorted(p_df["session_name"].unique().tolist()))
        e_f = st.selectbox("PDF Filter Exam", ["All"] + sorted(p_df["exam_label"].unique().tolist()))
        d_f = st.text_input("PDF Filter Day (YYYY-MM-DD)")
        out = p_df.copy()
        if s_f != "All": out = out[out["session_name"] == s_f]
        if e_f != "All": out = out[out["exam_label"] == e_f]
        if d_f: out = out[out["created_day"] == d_f]
        files = out["pdf_path"].tolist()
        if files:
            st.download_button("Bulk Download PDFs (ZIP)", download_zip_from_paths(files), file_name="admin_pdfs.zip", mime="application/zip")
