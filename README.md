# University RLE-RPV System (Enhanced Modular Streamlit)

Enhanced, modular Streamlit implementation with separate files for each role and configurable import/PDF layers.

## Highlights
- Single predefined CCF login: `BEAST / admin123`
- CCF-only lifecycle for all other users (create/edit/disable/delete)
- Session creation only requires session name
- Upload flow supports:
  - session selection
  - faculty selection
  - exam selection by **Exam Name + Program Code**
  - new exam creation with program code
- Exam search by name/program code while uploading
- Clerk enhancements:
  - visible current student status/remark/CGPI
  - auto-remove `RLE` remark when all GPIs are present
- Admin enhancements:
  - dashboard metrics
  - today/yesterday quick reports
  - combined filters: date range + session + exam + PRN + seat + status
  - approve/reject/suggest actions
  - PDF generation on approval
  - filtered CSV/Excel exports
  - filtered bulk PDF ZIP download
- Final member enhancements:
  - filter by session/exam/day
  - filtered CSV and Excel export
  - select-all filtered + bulk mark DONE/PENDING
- Audit tab + downloadable CSV logs
- SQLite dump/schema artifacts auto-updated

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Module Layout
- `app.py` -> entrypoint and role routing
- `db.py` -> DB schema/bootstrap/dump helpers
- `auth.py` -> password hashing
- `pages_ccf.py` -> CCF dashboard
- `pages_clerk.py` -> Clerk dashboard
- `pages_admin.py` -> Admin dashboard
- `pages_final.py` -> Final member dashboard
- `import_config.py` -> editable import column aliases
- `pdf_generator.py` -> editable PDF format generator

## Generated Artifacts
- `university_rle_rpv.db`
- `university_rle_rpv_schema.sql`
- `university_rle_rpv_dump.sql`
- `generated_letters/*.pdf`
