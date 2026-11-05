"""Tkinter dashboard for enrollment, recognition and attendance reports."""
import tkinter as tk
from datetime import date
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox, ttk

from config import CAMERA_INDEX, CAPTURE_COUNT, REPORTS
from src.recognize import recognize
from src.register_face import register
from src.reports import COLUMNS, export_report, report_data
from src.train_encodings import train
from src.vision import Vision

BG = "#edf2f7"
NAVY = "#14243b"
INK = "#152942"
MUTED = "#536780"
ACCENT = "#087c71"


class AttendanceApp:
    def __init__(self, root, db, demo=False):
        self.root, self.db, self.demo = root, db, demo
        self.events = Queue()
        self.stop = Event()
        self.busy = False
        self.closing = False
        self.status = tk.StringVar(value="Workspace ready")
        self.backend = tk.StringVar(value="opencv")
        self.camera = tk.StringVar(value=str(CAMERA_INDEX))
        today = date.today().isoformat()
        self.start = tk.StringVar(value=today)
        self.end = tk.StringVar(value=today)
        self.person = tk.StringVar()
        self.metrics = [tk.StringVar(value="0") for _ in range(3)]

        root.title("Facial Attendance System")
        root.geometry("1080x740")
        root.minsize(900, 650)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 7))
        style.configure("Primary.TButton", background=ACCENT, foreground="white")
        style.map("Primary.TButton", background=[("active", "#086b63"), ("disabled", "#a3bcb9")])
        style.configure("Treeview", rowheight=32, font=("Segoe UI", 10),
                        background="white", fieldbackground="white", foreground=INK)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TEntry", padding=5)
        self.build()
        self.refresh()
        root.after(100, self.poll)

    def build(self):
        header = tk.Frame(self.root, bg=NAVY, padx=24, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="ZZU COURSE PROJECT  /  DESKTOP WORKSPACE", bg=NAVY,
                 fg="#8fe1d5", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(header, text="Facial Attendance System", bg=NAVY, fg="white",
                 font=("Segoe UI", 24, "bold")).pack(anchor="w")
        text = "Demo workspace | Fictional records" if self.demo else "Enrollment and daily attendance"
        tk.Label(header, text=text, bg=NAVY, fg="#c0d1e6",
                 font=("Segoe UI", 10)).pack(anchor="w")

        body = tk.Frame(self.root, bg=BG, padx=24, pady=12)
        body.pack(fill="both", expand=True)
        cards = tk.Frame(body, bg=BG)
        cards.pack(fill="x")
        for index, title in enumerate(("Registered people", "Attendance records", "Calendar days in filter")):
            card = tk.Frame(cards, bg="white", padx=14, pady=7)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, bg="white", fg=MUTED,
                     font=("Segoe UI", 10)).pack(anchor="w")
            tk.Label(card, textvariable=self.metrics[index], bg="white", fg=INK,
                     font=("Segoe UI", 21, "bold")).pack(anchor="w")

        controls = tk.Frame(body, bg=BG, pady=10)
        controls.pack(fill="x")
        self.action_buttons = []
        for text, action in (
            ("Register New Face", self.enrollment_dialog),
            ("Train Model", self.start_training),
            ("Start Attendance", self.start_recognition),
        ):
            button = ttk.Button(controls, text=text, command=action, style="Primary.TButton")
            button.pack(side="left", padx=(0, 8))
            self.action_buttons.append(button)
        self.stop_button = ttk.Button(controls, text="Stop", command=self.request_stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(controls, text="Exit", command=self.close).pack(side="right")
        ttk.Combobox(controls, textvariable=self.backend, values=("opencv", "dlib"),
                     width=8, state="readonly").pack(side="right", padx=(4, 8))
        ttk.Entry(controls, textvariable=self.camera, width=3).pack(side="right", padx=4)
        tk.Label(controls, text="Camera", bg=BG, fg=MUTED).pack(side="right")

        filters = tk.Frame(body, bg=BG)
        filters.pack(fill="x", pady=(0, 8))
        for title, variable, width in (("From", self.start, 12), ("To", self.end, 12),
                                       ("Person ID", self.person, 13)):
            tk.Label(filters, text=title, bg=BG, fg=MUTED).pack(side="left", padx=(0, 4))
            ttk.Entry(filters, textvariable=variable, width=width).pack(side="left", padx=(0, 8))
        ttk.Button(filters, text="View Records", command=self.refresh).pack(side="left")
        ttk.Button(filters, text="Export Report", command=self.export).pack(side="right")

        tabs = ttk.Notebook(body)
        tabs.pack(fill="both", expand=True)
        self.records = self.table(tabs, "Daily records", COLUMNS,
                                  ("ID", "Name", "Date", "Time", "Status"))
        self.summary = self.table(tabs, "Attendance summary",
                                  ("id", "name", "present", "days", "percent"),
                                  ("ID", "Name", "Present days", "Calendar days", "Attendance %"))
        tk.Label(self.root, textvariable=self.status, anchor="w", bg=NAVY, fg="white",
                 padx=24, pady=8, font=("Segoe UI", 10)).pack(fill="x")
        if self.demo:
            for button in self.action_buttons:
                button.configure(state="disabled")

    def table(self, tabs, title, columns, headings):
        frame = ttk.Frame(tabs)
        tabs.add(frame, text=title)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        tree.tag_configure("alternate", background="#f1f6fb")
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=140, minwidth=75)
        return tree

    def refresh(self, announce=True):
        try:
            records, summary = self.filtered()
            for tree, rows in ((self.records, records), (self.summary, summary)):
                tree.delete(*tree.get_children())
                for index, values in enumerate(rows.itertuples(index=False, name=None)):
                    tree.insert("", "end", values=values, tags=("alternate",) if index % 2 else ())
            start, end = map(date.fromisoformat, (self.start.get(), self.end.get()))
            for variable, value in zip(self.metrics, (len(self.db.get_users()), len(records),
                                                       (end - start).days + 1)):
                variable.set(str(value))
            if announce:
                self.status.set(f"{len(records)} records shown | Dates use YYYY-MM-DD")
        except Exception as error:
            self.error(error)

    def filtered(self):
        return report_data(self.db, self.start.get(), self.end.get(), self.person.get())

    def export(self):
        try:
            records, summary = self.filtered()
            REPORTS.mkdir(parents=True, exist_ok=True)
            chosen = filedialog.asksaveasfilename(
                parent=self.root, initialdir=REPORTS, defaultextension=".xlsx",
                initialfile=f"attendance_{date.today()}.xlsx",
                filetypes=[("Excel workbook", "*.xlsx"), ("CSV file", "*.csv")],
            )
            if chosen:
                export_report(Path(chosen), records, summary)
                self.status.set(f"Exported {len(records)} records to {Path(chosen).name}")
        except Exception as error:
            self.error(error)

    def enrollment_dialog(self):
        dialog = tk.Toplevel(self.root, padx=18, pady=16)
        dialog.title("Register New Face")
        dialog.transient(self.root)
        dialog.grab_set()
        entries = []
        for row, title in enumerate(("Student / employee ID", "Full name", "Department")):
            ttk.Label(dialog, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            field = ttk.Entry(dialog, width=30)
            field.grid(row=row, column=1, pady=5)
            entries.append(field)
        entries[0].focus_set()
        ttk.Label(dialog, text=f"Capture {CAPTURE_COUNT} single-face samples with Space.").grid(
            row=3, columnspan=2, sticky="w", pady=8)

        def submit():
            values = [field.get() for field in entries]
            try:
                backend, camera = self.settings()
            except ValueError as error:
                messagebox.showerror("Camera settings", str(error), parent=dialog)
                return
            dialog.destroy()

            def task():
                saved = register(self.db, Vision(backend), camera, self.stop, *values)
                return "Registration saved. Train Model before recognizing this person." if saved else "Registration cancelled."

            self.run_task("Opening enrollment camera...", task)

        ttk.Button(dialog, text="Start capture", command=submit).grid(row=4, column=1, sticky="e")
        dialog.bind("<Escape>", lambda _: dialog.destroy())

    def settings(self):
        camera = int(self.camera.get())
        if camera < 0:
            raise ValueError("Camera index must be zero or greater.")
        return self.backend.get(), camera

    def start_training(self):
        backend = self.backend.get()
        self.run_task("Encoding enrollment images...",
                      lambda: train(self.db, Vision(backend), self.stop, self.progress))

    def start_recognition(self):
        try:
            backend, camera = self.settings()
            self.run_task("Starting attendance camera...",
                          lambda: recognize(self.db, Vision(backend), camera, self.stop, self.progress))
        except ValueError as error:
            self.error(error)

    def run_task(self, message, task):
        if self.busy:
            return
        self.busy = True
        self.stop.clear()
        self.status.set(message)
        for button in self.action_buttons:
            button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        def worker():
            try:
                self.events.put(("done", task()))
            except Exception as error:
                self.events.put(("error", str(error)))

        Thread(target=worker, daemon=True).start()

    def progress(self, message):
        self.events.put(("progress", message))

    def poll(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == "progress":
                    if not self.closing:
                        self.status.set(message)
                    continue
                self.busy = False
                if self.closing:
                    self.root.destroy()
                    return
                self.stop_button.configure(state="disabled")
                for button in self.action_buttons:
                    button.configure(state="normal")
                if kind == "error":
                    self.error(message)
                else:
                    self.refresh(announce=False)
                    self.status.set(message)
        except Empty:
            pass
        self.root.after(100, self.poll)

    def request_stop(self):
        self.stop.set()
        self.status.set("Stopping after the current operation...")

    def error(self, error):
        self.status.set("Action could not be completed")
        messagebox.showerror("Attendance workspace", str(error), parent=self.root)

    def close(self):
        if self.busy:
            self.closing = True
            self.request_stop()
        else:
            self.root.destroy()
