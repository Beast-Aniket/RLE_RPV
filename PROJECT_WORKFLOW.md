# RLE-RPV Project Workflow (Draft v1)

This document converts your rough idea into a clear end-to-end workflow for implementation and team alignment.

---

## 1) Objective

Build a role-based result-correction workflow system for **RLE** and **RPV** cases, with:
- Session-wise upload by CCF
- Faculty-wise clerk processing
- Faculty admin review/approval
- Final marksheet-generation team download and completion tracking

---

## 2) Roles and Access

## 2.1 CCF (Central Control Faculty / Super User)
**Responsibilities:**
- Create exam sessions (example: *April 2025*)
- Upload source result data (`.dbf` or `.xlsx`) session-wise
- Create/manage login credentials for:
  - Faculty Clerks (faculty-specific)
  - Faculty Admins (faculty-specific)
  - Final processing team (marksheet generator)

## 2.2 Faculty Clerk (Faculty-specific login)
Separate login per faculty:
- Science & Technology
- Commerce & Management
- Interdisciplinary
- Humanities

**Responsibilities:**
- Select session created by CCF
- Search student via PRN or Seat Number
- Enter/update missing GPI values (Sem 1–Sem 6)
- Handle RLE and RPV actions
- Submit request to Faculty Admin
- Track status (Approved / Rejected / Suggested Edit)

## 2.3 Faculty Admin (Faculty-specific login)
**Responsibilities:**
- Review clerk-submitted requests
- Filter/review by type (RLE, RPV, marks edited, etc.)
- Approve / Reject / Suggest Edit
- On approval: trigger standardized letter generation

## 2.4 Final Member (Marksheet Generator login, created by CCF)
**Responsibilities:**
- View approved entries in date-wise + session-wise pending buckets
- Open and download generated letters (bulk or selected)
- Download day-wise Excel export of edited records
- Mark records as Done / Pending (manual override allowed)
- Raise Query for incorrect entries

---

## 3) Core Data Visible During Clerk Processing

When clerk searches a student record, show:
- Name
- PRN
- Sex
- CGPI
- GCGPI (Ordinance)
- Sem1 GPI to Sem6 GPI
- Remark
- Result Status

### CGPI Rule
If any semester GPI is missing and clerk adds value(s), system auto-recalculates CGPI.

---

## 4) Business Workflow by Stage

## Stage A: Session Setup & Data Upload (CCF)
1. CCF creates session (example: April 2025).
2. CCF uploads master result file (`.dbf` / `.xlsx`) mapped to that session.
3. System validates file format and required columns.
4. Records become searchable to relevant faculty users.

## Stage B: Clerk Processing (Faculty-wise)
1. Clerk logs in (faculty-scoped access only).
2. Clerk selects session.
3. Clerk searches student (PRN / Seat No).
4. Clerk checks current details and status.

### B1: RLE flow
- If GPIs are missing:
  - Clerk enters missing semester GPI values
  - CGPI auto-calculates
  - Clerk submits for Admin review

### B2: RPV flow
- If status is RPV:
  - Clerk removes RPV remark
  - Marks student as Eligible
  - Submits for Admin review

5. Clerk dashboard tabs:
- Pending with Admin
- Approved
- Rejected
- Suggested Edit (returned by Admin for correction)

## Stage C: Admin Review & Decision (Faculty-wise)
1. Admin logs in and opens incoming clerk requests.
2. Admin can filter/select random series or targeted categories:
   - RLE requests
   - RPV requests
   - Marks/CGPI edits
3. Admin reviews change history and record details.
4. Admin chooses one outcome:
   - **Approve** → moves to Approved tab + letter generation queue
   - **Reject** → moves to Rejected tab (with reason)
   - **Suggest Edit** → moves to Suggested Edit tab (with comments back to clerk)

## Stage D: Letter Generation (Post-Approval)
1. For each approved record, system generates letter in standard format.
2. Letter is linked to student record + session + faculty + approval timestamp.
3. Generated letters become available in Final Member login.

## Stage E: Final Processing (Marksheet Generator)
1. Final member logs in.
2. Dashboard shows pending workload grouped by:
   - Session (example: April 2024 BMS)
   - Date bucket (example: 01-01-2025)
   - Pending count (example: 24 records)
3. User opens group to:
   - View generated letters
   - Download all letters or selected letters
   - Download corresponding day-wise Excel edited data
4. After processing:
   - Mark all as Done (system timestamp)
   - or manually set Pending/Done
   - or Raise Query on wrong entry

---

## 5) Status Model (Recommended)

Use consistent status lifecycle:

1. `DRAFT` (optional internal)
2. `SUBMITTED_BY_CLERK`
3. `ADMIN_APPROVED`
4. `ADMIN_REJECTED`
5. `ADMIN_SUGGESTED_EDIT`
6. `RESUBMITTED_BY_CLERK`
7. `LETTER_GENERATED`
8. `FINAL_PENDING`
9. `FINAL_DONE`
10. `FINAL_QUERY_RAISED`

This ensures auditability and easy dashboard filters.

---

## 6) Key Screens (Suggested)

1. **CCF Panel**
   - Session Management
   - File Upload
   - User/Credential Management

2. **Clerk Panel**
   - Session Selector
   - Student Search
   - RLE/RPV Edit Form
   - My Requests with status tabs

3. **Admin Panel**
   - Request Inbox
   - Filters + bulk selection
   - Approve / Reject / Suggest Edit actions
   - Approved/Rejected/Suggested tabs

4. **Final Processing Panel**
   - Date-wise + Session-wise pending grid
   - Letter viewer and downloader
   - Day-wise Excel downloader
   - Done/Pending/Query actions

---

## 7) Audit & Compliance Requirements

Track all major actions with timestamp and user id:
- File upload
- Field-level edits (old value → new value)
- Submission and resubmission
- Admin decision + comments
- Letter generation event
- Final done/pending/query updates

Keep an immutable audit trail for accountability.

---

## 8) Notifications (Optional but Useful)

- Clerk gets notification for Admin Reject/Suggest Edit.
- Admin gets notification for new clerk submission.
- Final member gets notification for newly approved + letter-generated batch.

---

## 9) Edge Cases to Handle

- Duplicate PRN/Seat mapping conflict
- Invalid GPI range entry
- Missing semester data in upload file
- Same record edited by two users simultaneously (locking/versioning)
- RPV removed without required remarks justification
- Bulk download limits/timeouts

---

## 10) Next Step Inputs Needed From You

To finalize into implementation-ready SRS/UI flow, share:
1. Standard letter format template
2. Exact Excel/DBF schema (mandatory columns)
3. Faculty-program mapping rules
4. Approval authority matrix (who can approve what)
5. Query resolution workflow (who closes final queries)
6. Required reports and export formats

---

## 11) One-Line Workflow Summary

**CCF creates session + uploads data → Clerk edits RLE/RPV and submits → Faculty Admin approves/rejects/suggests edits → Approved cases generate letters → Final team downloads letters/excel and marks completion/query with timestamps.**
