import io
import os

import pandas as pd
import streamlit as st

from db import commit_db, now


def audit(conn, action, entity_type, entity_id=None, message=""):
    conn.execute(
        "INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,message,created_at) VALUES(?,?,?,?,?,?)",
        (st.session_state.get("username"), action, entity_type, entity_id, message, now()),
    )


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="FinalReport")
    buffer.seek(0)
    return buffer.read()


def render_final_page(conn):
    st.subheader("Final Member (Generator) Dashboard")

    rows = conn.execute(
        """SELECT er.id as request_id, er.status as admin_status, s.session_name, e.exam_name, e.program_code,
        st.name, st.prn, st.seat_no, l.pdf_path, date(er.created_at) as request_day,
        COALESCE(fa.final_state,'PENDING') as final_state, fa.final_comment
        FROM edit_requests er
        JOIN students st ON st.id=er.student_id
        JOIN sessions s ON s.id=er.session_id
        JOIN exams e ON e.id=er.exam_id
        LEFT JOIN letters l ON l.request_id=er.id
        LEFT JOIN final_actions fa ON fa.request_id=er.id
        WHERE er.status='ADMIN_APPROVED'
        ORDER BY er.id DESC"""
    ).fetchall()
    if not rows:
        st.info("No approved requests")
        return

    df = pd.DataFrame([dict(x) for x in rows])
    df["exam_label"] = df["exam_name"] + " (" + df["program_code"] + ")"

    m1, m2, m3 = st.columns(3)
    m1.metric("Pending", int((df["final_state"] == "PENDING").sum()))
    m2.metric("Done", int((df["final_state"] == "DONE").sum()))
    m3.metric("Query", int((df["final_state"] == "QUERY").sum()))

    c1, c2, c3 = st.columns(3)
    session_filter = c1.selectbox("Session", ["All"] + sorted(df["session_name"].unique().tolist()))
    exam_filter = c2.selectbox("Exam", ["All"] + sorted(df["exam_label"].unique().tolist()))
    day_filter = c3.text_input("Day (YYYY-MM-DD)")

    out = df.copy()
    if session_filter != "All":
        out = out[out["session_name"] == session_filter]
    if exam_filter != "All":
        out = out[out["exam_label"] == exam_filter]
    if day_filter:
        out = out[out["request_day"] == day_filter]

    st.dataframe(out[["request_id", "session_name", "exam_label", "name", "prn", "seat_no", "request_day", "final_state"]], use_container_width=True)
    st.download_button("Download Filtered CSV", out.to_csv(index=False).encode("utf-8"), file_name="final_filtered_entries.csv", mime="text/csv")
    st.download_button("Download Filtered Excel", dataframe_to_excel_bytes(out), file_name="final_filtered_entries.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    ids = out["request_id"].tolist()
    select_all = st.checkbox("Select all filtered IDs")
    selected = ids if select_all else st.multiselect("Select request IDs", ids)

    a1, a2 = st.columns(2)
    if a1.button("Mark Selected DONE") and selected:
        for rid in selected:
            conn.execute(
                "INSERT INTO final_actions(request_id,final_state,final_comment,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET final_state=excluded.final_state, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (int(rid), "DONE", None, st.session_state["user_id"], now()),
            )
            audit(conn, "FINAL_MARK_DONE", "final_actions", int(rid), "bulk done")
        commit_db(conn)
        st.success("Selected marked DONE")
        st.rerun()

    if a2.button("Mark Selected PENDING") and selected:
        for rid in selected:
            conn.execute(
                "INSERT INTO final_actions(request_id,final_state,final_comment,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET final_state=excluded.final_state, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (int(rid), "PENDING", None, st.session_state["user_id"], now()),
            )
            audit(conn, "FINAL_MARK_PENDING", "final_actions", int(rid), "bulk pending")
        commit_db(conn)
        st.warning("Selected marked PENDING")
        st.rerun()

    if not out.empty:
        first = out.iloc[0]
        if first.get("pdf_path") and os.path.exists(first["pdf_path"]):
            st.markdown("### PDF Access")
            with open(first["pdf_path"], "rb") as f:
                st.download_button("Download first filtered PDF", f.read(), file_name=os.path.basename(first["pdf_path"]), mime="application/pdf")
