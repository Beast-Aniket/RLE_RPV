# University RLE-RPV System (Streamlit)

A complete Streamlit-based university workflow system with:
- Fixed CCF login: `BEAST / admin123`
- All other users created/managed by CCF (create/modify/disable)
- Exam + Session creation with faculty mapping
- Faculty-specific visibility (users see only assigned faculty exam/session data)
- Result file upload (`.csv`, `.xlsx`, `.dbf`)
- Clerk submission flow for RLE/RPV edits
- Faculty Admin approval/rejection/suggest flow
- Final section for letter processing and final states
- Auto-created SQL artifacts in run directory

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Database files generated automatically
- `university_rle_rpv.db`
- `university_rle_rpv_schema.sql`
- `university_rle_rpv_dump.sql`

## Default Login
- CCF only: `BEAST / admin123`
