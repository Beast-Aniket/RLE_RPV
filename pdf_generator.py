import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def ensure_letters_dir():
    path = "generated_letters"
    os.makedirs(path, exist_ok=True)
    return path


def generate_letter_pdf(student_row, request_row, payload, admin_comment):
    base = ensure_letters_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"letter_req_{request_row['id']}_{student_row['prn']}_{ts}.pdf"
    file_path = os.path.join(base, file_name)

    c = canvas.Canvas(file_path, pagesize=A4)
    y = 800
    lines = [
        "UNIVERSITY RESULT CORRECTION LETTER",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Session: {request_row['session_name']}",
        f"Exam: {request_row['exam_name']} ({request_row['program_code']})",
        f"Faculty: {student_row['faculty']}",
        f"Student: {student_row['name']} ({student_row['prn']})",
        f"Seat No: {student_row['seat_no']}",
        f"Result Status: {payload.get('result_status')}",
        f"CGPI: {payload.get('cgpi')}",
        f"Remark: {payload.get('remark')}",
        f"Admin Comment: {admin_comment or 'Approved'}",
        "",
        "This is a system generated document.",
    ]

    for line in lines:
        c.drawString(50, y, str(line))
        y -= 20
    c.save()
    return file_path
