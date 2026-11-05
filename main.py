"""Launch the Facial Attendance System desktop app."""
import argparse
import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import messagebox

from src.db_manager import Database
from src.gui import AttendanceApp


def start(path=None):
    root = tk.Tk()
    try:
        db = Database() if path is None else Database(path)
        if path is not None:
            for key, name, department in (
                ("DEMO01", "Alex Chen", "Software Engineering"),
                ("DEMO02", "Mina Rahman", "Computer Science"),
                ("DEMO03", "Sam Lee", "Information Systems"),
            ):
                db.add_user(key, name, department)
            for key, hour, minute in (("DEMO01", 9, 4), ("DEMO02", 9, 8)):
                db.mark_attendance(key, datetime.now().replace(hour=hour, minute=minute, second=0))
        AttendanceApp(root, db, demo=path is not None)
    except (OSError, sqlite3.Error) as error:
        messagebox.showerror("Could not open workspace", str(error), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Open a workspace with fictional records")
    if parser.parse_args().demo:
        with TemporaryDirectory(prefix="attendance-demo-") as directory:
            raise SystemExit(start(Path(directory) / "demo.db"))
    raise SystemExit(start())
