from contextlib import closing

import streamlit as st

from auth import hash_password
from db import DUMP_FILE, bootstrap_db, connect_db
from pages_admin import render_admin_page
from pages_ccf import render_ccf_page
from pages_clerk import render_clerk_page
from pages_final import render_final_page


def login_view(conn):
    st.title("University RLE-RPV System")
    st.caption("Single predefined login: CCF (BEAST/admin123). All other users are CCF-managed.")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login", use_container_width=True):
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password_hash=? AND is_active=1",
            (username, hash_password(password)),
        ).fetchone()
        if row:
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = row["id"]
            st.session_state["username"] = row["username"]
            st.session_state["role"] = row["role"]
            st.session_state["faculty"] = row["faculty"]
            st.rerun()
        else:
            st.error("Invalid credentials")


def app_shell():
    st.set_page_config(page_title="University RLE-RPV", layout="wide")
    bootstrap_db(hash_password("admin123"))

    with closing(connect_db()) as conn:
        if not st.session_state.get("logged_in"):
            login_view(conn)
            return

        with st.sidebar:
            st.write(f"**User:** {st.session_state.get('username')}")
            st.write(f"**Role:** {st.session_state.get('role')}")
            if st.session_state.get("faculty"):
                st.write(f"**Faculty:** {st.session_state.get('faculty')}")
            if st.button("Logout"):
                st.session_state.clear()
                st.rerun()
            if st.session_state.get("role") == "CCF":
                st.write(f"SQL dump: `{DUMP_FILE}`")

        role = st.session_state.get("role")
        if role == "CCF":
            render_ccf_page(conn)
        elif role == "CLERK":
            render_clerk_page(conn)
        elif role == "ADMIN":
            render_admin_page(conn)
        elif role == "FINAL":
            render_final_page(conn)
        else:
            st.error("Role not configured")


if __name__ == "__main__":
    app_shell()
