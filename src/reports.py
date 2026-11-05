"""Attendance filtering, summary and spreadsheet export."""
from datetime import date
from pathlib import Path

import pandas as pd

COLUMNS = ["student_id", "name", "date", "time", "status"]


def report_data(db, start: str, end: str, student_id: str = ""):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError("End date must be on or after start date.")
    from src.db_manager import student_key
    key = student_key(student_id) if student_id.strip() else None
    rows = db.get_attendance(student_id=key, start=first.isoformat(), end=last.isoformat())
    records = pd.DataFrame([dict(row) for row in rows], columns=COLUMNS)
    days = (last - first).days + 1
    counts = records["student_id"].value_counts()
    summary = []
    for user in db.get_users():
        uid = user["student_id"]
        if key is None or uid == key:
            present = int(counts.get(uid, 0))
            summary.append([uid, user["name"], present, days, round(present * 100 / days, 2)])
    columns = ["student_id", "name", "present_days", "calendar_days", "attendance_percent"]
    return records, pd.DataFrame(summary, columns=columns)


def export_report(path: Path, records, summary) -> None:
    def safe_text(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    records, summary = records.copy(), summary.copy()
    for frame in (records, summary):
        frame["name"] = frame["name"].map(safe_text)
    if path.suffix.lower() == ".csv":
        records.to_csv(path, index=False, encoding="utf-8-sig")
    elif path.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            records.to_excel(writer, sheet_name="Attendance", index=False)
            summary.to_excel(writer, sheet_name="Summary", index=False)
    else:
        raise ValueError("Choose an .xlsx or .csv file.")
