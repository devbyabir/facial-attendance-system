"""SQLite storage for enrollment and daily attendance."""
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config import DATABASE


def student_key(value: str) -> str:
    """Normalize a student ID for use in SQLite and dataset paths."""
    key = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,31}", key):
        raise ValueError("ID must contain 1-32 letters, numbers, hyphens or underscores.")
    return key


class Database:
    def __init__(self, path: Path = DATABASE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    student_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY,
                    student_id TEXT NOT NULL REFERENCES users(student_id),
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Present',
                    UNIQUE(student_id, date)
                );
                CREATE INDEX IF NOT EXISTS attendance_date ON attendance(date);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

    def add_user(self, student_id: str, name: str, department: str) -> None:
        key = student_key(student_id)
        name, department = name.strip(), department.strip()
        if not name or not department:
            raise ValueError("Name and department are required.")
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO users(student_id, name, department, registered_at)
                   VALUES (?, ?, ?, ?) ON CONFLICT(student_id) DO NOTHING""",
                (key, name, department, datetime.now().isoformat(timespec="seconds")),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Student ID {key} is already registered.")

    def get_users(self):
        with self.connect() as db:
            return db.execute("SELECT * FROM users ORDER BY name, student_id").fetchall()

    def mark_attendance(self, student_id: str, when: datetime | None = None) -> bool:
        key = student_key(student_id)
        when = when or datetime.now()
        with self.connect() as db:
            user = db.execute("SELECT name FROM users WHERE student_id = ?", (key,)).fetchone()
            if user is None:
                raise ValueError(f"Unknown student ID: {key}")
            cursor = db.execute(
                """INSERT INTO attendance(student_id, name, date, time)
                   VALUES (?, ?, ?, ?) ON CONFLICT(student_id, date) DO NOTHING""",
                (key, user["name"], when.date().isoformat(), when.strftime("%H:%M:%S")),
            )
            return cursor.rowcount == 1

    def get_attendance(self, date: str | None = None, student_id: str | None = None,
                       *, start: str | None = None, end: str | None = None):
        if date is not None:
            start = end = date
        filters, params = [], []
        if start:
            filters.append("date >= ?")
            params.append(start)
        if end:
            filters.append("date <= ?")
            params.append(end)
        if student_id:
            filters.append("student_id = ?")
            params.append(student_key(student_id))
        where = " WHERE " + " AND ".join(filters) if filters else ""
        with self.connect() as db:
            return db.execute(
                "SELECT student_id, name, date, time, status FROM attendance"
                + where + " ORDER BY date DESC, time DESC, student_id",
                params,
            ).fetchall()
