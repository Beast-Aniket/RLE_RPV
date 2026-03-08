# RLE-RPV University Dashboard (Advanced Flask Version)

This project provides a full role-based university workflow for RLE/RPV correction processing.

## Core modules implemented
- CCF Control Center: session creation, faculty-wise upload, SQL dump export, audit logs
- Faculty Clerk Desk: search PRN/Seat, edit sem GPIs, RLE/RPV handling, submit/resubmit requests
- Faculty Admin Desk: filter by status, approve/reject/suggest edits, letter generation
- Final Processing Desk: date/session summary, final state updates, bulk letter download, day report CSV

## Database artifacts created in running directory
When app starts, it creates:
- `rle_rpv.db` (SQLite operational database)
- `rle_rpv_schema.sql` (schema SQL file)
- `rle_rpv_dump.sql` (full SQL dump updated after each write action)

## Quick run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://localhost:5000`

## Default users
- CCF: `ccf / ccf123`
- Faculty Clerk: `clerk_snt / clerk123`, `clerk_com / clerk123`, `clerk_inter / clerk123`, `clerk_hum / clerk123`
- Faculty Admin: `admin_snt / admin123`, `admin_com / admin123`, `admin_inter / admin123`, `admin_hum / admin123`
- Final Member: `final_member / final123`

## Upload format
Supported: `.csv`, `.xlsx`, `.dbf`

Columns (recommended):
- `name`, `prn`, `seat_no`, `sex`
- `sem1`, `sem2`, `sem3`, `sem4`, `sem5`, `sem6`
- `gcgpi`, `remark`, `result_status`

Use sample file `sample_students.csv` for testing.
