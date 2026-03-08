# University RLE-RPV System (Streamlit, Modular)

This is a modular Streamlit implementation with separate files for each role and utilities.

## Key changes
- Fixed predefined CCF login only: `BEAST / admin123`
- CCF-only user management (create/edit/disable users and assign role/faculty)
- Session creation without start/end date
- Upload flow includes exam name + program code management
- Faculty-scoped data visibility
- Clerk auto-removes `RLE` remark when all GPIs are entered
- Admin advanced filters + PRN/Seat search + PDF generation + bulk PDF ZIP download
- Final member filters + export filtered data + bulk mark done/pending
- Separate file for import standards (`import_config.py`)
- Separate file for PDF generation (`pdf_generator.py`)

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Modules
- `app.py` -> entrypoint + routing by role
- `db.py` -> schema/bootstrap/db dump
- `auth.py` -> password hashing
- `pages_ccf.py` -> CCF dashboard
- `pages_clerk.py` -> clerk dashboard
- `pages_admin.py` -> admin dashboard
- `pages_final.py` -> final member dashboard
- `import_config.py` -> import column aliases
- `pdf_generator.py` -> PDF format generator

## Generated artifacts
- `university_rle_rpv.db`
- `university_rle_rpv_schema.sql`
- `university_rle_rpv_dump.sql`
- `generated_letters/*.pdf`
