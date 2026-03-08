import json

import pandas as pd
import streamlit as st

from db import commit_db, now


def parse_float(v):
    if v in (None, ""):
        return None
    return float(v)


def calc_cgpi(row):
    vals = [row.get(f"sem{i}") for i in range(1, 7)]
    vals = [float(v) for v in vals if v not in (None, "")]
    return round(sum(vals) / len(vals), 2) if vals else None


def audit(conn, action, entity_type, entity_id=None, message=""):
    conn.execute(
        "INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,message,created_at) VALUES(?,?,?,?,?,?)",
        (st.session_state.get("username"), action, entity_type, entity_id, message, now()),
    )


def render_clerk_page(conn):
    faculty = st.session_state.get("faculty")
    st.subheader(f"Clerk Dashboard - {faculty}")

    sessions = conn.execute(
        """SELECT s.id, s.session_name, e.exam_name, e.program_code, e.id as exam_id
        FROM sessions s
        JOIN students st ON st.session_id=s.id
        JOIN exams e ON e.id=st.exam_id
        WHERE st.faculty=?
        GROUP BY s.id, e.id
        ORDER BY s.id DESC""",
        (faculty,),
    ).fetchall()
    if not sessions:
        st.info("No session/exam mapped data for your faculty")
        return

    options = {f"{r['session_name']} | {r['exam_name']} ({r['program_code']})": r for r in sessions}
    selected = options[st.selectbox("Select Session + Exam", list(options.keys()))]

    q = st.text_input("Search student by PRN or Seat No")
    if q:
        st_row = conn.execute(
            "SELECT * FROM students WHERE session_id=? AND exam_id=? AND faculty=? AND (prn=? OR seat_no=?)",
            (selected["id"], selected["exam_id"], faculty, q.strip(), q.strip()),
        ).fetchone()
        if not st_row:
            st.warning("Student not found")
        else:
            st.success(f"{st_row['name']} | PRN: {st_row['prn']}")
            sem = {}
            cols = st.columns(6)
            for i in range(1, 7):
                sem[f"sem{i}"] = cols[i - 1].text_input(f"Sem{i}", value="" if st_row[f"sem{i}"] is None else str(st_row[f"sem{i}"]))
            remark = st.text_input("Remark", value=st_row["remark"] or "")
            result_status = st.text_input("Result Status", value=st_row["result_status"] or "")

            if st.button("Submit to Admin"):
                parsed = {k: parse_float(v) for k, v in sem.items()}
                all_gpi_present = all(parsed.get(f"sem{i}") is not None for i in range(1, 7))
                updated_remark = remark.strip()
                if all_gpi_present and "RLE" in updated_remark.upper():
                    updated_remark = " ".join([x for x in updated_remark.split() if x.upper() != "RLE"]).strip()

                payload = {
                    **parsed,
                    "remark": updated_remark,
                    "result_status": result_status.strip(),
                    "cgpi": calc_cgpi(parsed),
                }
                req_type = "RPV" if (st_row["result_status"] or "").upper() == "RPV" else "RLE"
                conn.execute(
                    """INSERT INTO edit_requests(student_id,session_id,exam_id,faculty,submitted_by,request_type,status,payload_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        st_row["id"],
                        selected["id"],
                        selected["exam_id"],
                        faculty,
                        st.session_state["user_id"],
                        req_type,
                        "SUBMITTED_BY_CLERK",
                        json.dumps(payload),
                        now(),
                        now(),
                    ),
                )
                audit(conn, "SUBMIT_REQUEST", "edit_requests", message=f"student={st_row['prn']}")
                commit_db(conn)
                st.success("Submitted")

    reqs = conn.execute(
        """SELECT er.id, er.request_type, er.status, er.admin_comment, er.created_at, st.name, st.prn
        FROM edit_requests er JOIN students st ON st.id=er.student_id
        WHERE er.submitted_by=? ORDER BY er.id DESC""",
        (st.session_state["user_id"],),
    ).fetchall()
    if reqs:
        st.markdown("### My Requests")
        st.dataframe(pd.DataFrame([dict(x) for x in reqs]), use_container_width=True)
