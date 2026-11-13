"""Tkinter dashboard for enrollment, recognition and attendance reports."""
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox, ttk

from config import CAMERA_INDEX, CAPTURE_COUNT, REPORTS
from src.camera import read_frame, webcam
from src.recognize import recognize
from src.register_face import register
from src.reports import COLUMNS, export_report, report_data
from src.train_encodings import index_path, load_index, train
from src.vision import Vision

BG = "#f4f6fb"
SURFACE = "#ffffff"
NAVY = "#172136"
INK = "#19243a"
MUTED = "#536178"
ACCENT = "#3e51bf"
LINE = "#dbe2ef"
FONT = "Segoe UI"


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
        self.start = tk.StringVar(value=self.default_start())
        self.model_state = tk.StringVar()
        self.camera_state = tk.StringVar(value="Demo does not use a camera" if demo else "Camera not checked")
        self.record_state = tk.StringVar()
        self.people_state = tk.StringVar()
        self.encoded_ids = set()
        self.end = tk.StringVar(value=today)
        self.person = tk.StringVar()
        self.applied_filters = (self.start.get(), self.end.get(), "")
        self.metrics = [tk.StringVar(value="0") for _ in range(3)]

        root.title("Facial Attendance System")
        root.geometry("1180x760")
        root.minsize(900, 650)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.configure_styles()
        self.build()
        self.refresh(announce=False)
        self.backend.trace_add("write", self.settings_changed)
        self.camera.trace_add("write", self.camera_changed)
        root.after(100, self.poll)

    def configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=(FONT, 10), background=BG, foreground=INK)
        style.configure("TButton", padding=(12, 7), background=SURFACE, bordercolor=LINE)
        style.map("TButton", background=[("active", "#e9edfa")],
                  bordercolor=[("focus", ACCENT)])
        style.configure("Primary.TButton", background=ACCENT, foreground="white")
        style.map("Primary.TButton", background=[("disabled", "#e3e8f4"), ("active", "#30429e")],
                  foreground=[("disabled", MUTED)], bordercolor=[("focus", NAVY)])
        style.configure("Nav.TButton", anchor="w", padding=(12, 10),
                        background=NAVY, foreground="#d1daed", bordercolor=NAVY)
        style.map("Nav.TButton", background=[("selected", "#35436d"), ("active", "#273553")],
                  bordercolor=[("focus", "#a9b8f2")])
        style.configure("Treeview", rowheight=34, background=SURFACE,
                        fieldbackground=SURFACE, foreground=INK, bordercolor=LINE)
        style.map("Treeview", background=[("selected", "#dce4fc")],
                  foreground=[("selected", INK)])
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"), padding=8,
                        background="#e9eef8", bordercolor=LINE)
        style.configure("TEntry", padding=6, fieldbackground=SURFACE, bordercolor=LINE)
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("TCombobox", padding=6, fieldbackground=SURFACE, bordercolor=LINE)
        style.map("TCombobox", bordercolor=[("focus", ACCENT)])
        style.configure("TNotebook", bordercolor=LINE)
        style.configure("TNotebook.Tab", padding=(12, 7))

    def default_start(self):
        return (date.today() - timedelta(days=4 if self.demo else 0)).isoformat()

    def label(self, parent, text="", *, variable=None, size=11, bold=False, color=INK):
        return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget("bg"),
                        fg=color, font=(FONT, size, "bold" if bold else "normal"),
                        anchor="w", justify="left")

    def card(self, parent):
        return tk.Frame(parent, bg=SURFACE, highlightbackground=LINE, highlightthickness=1,
                        padx=18, pady=14)

    def build(self):
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=NAVY, width=200, padx=16, pady=24)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.label(sidebar, "Facial Attendance", size=13, bold=True, color="white").pack(anchor="w")
        self.label(sidebar, "DEMO WORKSPACE" if self.demo else "LOCAL WORKSPACE",
                   size=9, color="#b8c5df").pack(anchor="w", pady=(4, 24))

        main = tk.Frame(shell, bg=BG, padx=24, pady=18)
        main.pack(side="left", fill="both", expand=True)
        self.status_bar = self.label(main, variable=self.status, size=10, color=MUTED)
        self.status_bar.pack(side="bottom", fill="x", pady=(10, 0))
        self.pages, self.navigation = {}, {}
        for name in ("Overview", "People", "Attendance Records", "Settings"):
            self.pages[name] = tk.Frame(main, bg=BG)
            button = ttk.Button(sidebar, text=name, style="Nav.TButton",
                                command=lambda page=name: self.navigate(page))
            button.pack(fill="x", pady=(0, 4))
            self.navigation[name] = button
        self.stop_button = ttk.Button(sidebar, text="Stop current task",
                                      command=self.request_stop, state="disabled")
        self.stop_button.pack(side="bottom", fill="x")
        self.action_buttons = []
        self.settings_inputs = []
        self.build_overview()
        self.build_people()
        self.build_records()
        self.build_settings()
        self.navigate("Overview")
        self.update_controls()

    def navigate(self, name):
        for page, frame in self.pages.items():
            self.navigation[page].state(["selected" if page == name else "!selected"])
            frame.pack_forget()
        self.pages[name].pack(fill="both", expand=True)

    def heading(self, parent, title, description):
        self.label(parent, title, size=23, bold=True).pack(anchor="w")
        self.label(parent, description, color=MUTED).pack(anchor="w", pady=(2, 16))

    def action(self, parent, title, command, *, primary=False):
        button = ttk.Button(parent, text=title, command=command,
                            style="Primary.TButton" if primary else "TButton")
        self.action_buttons.append(button)
        return button

    def build_overview(self):
        page = self.pages["Overview"]
        self.heading(page, "Overview", "Daily attendance and workspace readiness")
        metrics = tk.Frame(page, bg=BG)
        metrics.pack(fill="x")
        for i, title in enumerate(("Registered people", "Present today", "Last attendance")):
            metrics.columnconfigure(i, weight=1, uniform="metrics")
            card = self.card(metrics)
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 10) if i < 2 else 0)
            self.label(card, title, color=MUTED).pack(anchor="w")
            self.label(card, variable=self.metrics[i], size=20 if i < 2 else 14,
                       bold=True).pack(anchor="w", pady=(6, 2))

        session = self.card(page)
        session.pack(fill="x", pady=(14, 0))
        self.label(session, "Attendance session", size=14, bold=True).pack(anchor="w")
        self.label(session, "Register a person, generate encodings, then start attendance.",
                   color=MUTED).pack(anchor="w", pady=(4, 12))
        self.label(session, variable=self.model_state).pack(anchor="w")
        self.label(session, variable=self.camera_state, color=MUTED).pack(anchor="w", pady=(2, 12))
        controls = tk.Frame(session, bg=SURFACE)
        controls.pack(fill="x")
        self.start_button = self.action(controls, "Start Attendance", self.start_recognition,
                                        primary=True)
        self.start_button.pack(side="left")
        ttk.Button(controls, text="Camera and model settings",
                   command=lambda: self.navigate("Settings")).pack(side="left", padx=8)

        recent = tk.Frame(page, bg=BG)
        recent.pack(fill="both", expand=True, pady=(14, 0))
        self.label(recent, "Recent attendance", size=14, bold=True).pack(anchor="w", pady=(0, 6))
        self.recent = self.table(recent, COLUMNS, ("ID", "Name", "Date", "Time", "Status"))
        self.recent.configure(height=4)
        self.recent_empty = self.label(recent, "No attendance has been recorded yet.", color=MUTED)

    def build_people(self):
        page = self.pages["People"]
        self.heading(page, "People", "Manage enrollment and see who has usable face encodings.")
        controls = tk.Frame(page, bg=BG)
        controls.pack(fill="x", pady=(0, 10))
        self.action(controls, "Register Person", self.enrollment_dialog, primary=True).pack(side="left")
        self.label(controls, variable=self.people_state, color=MUTED).pack(side="left", padx=12)
        self.people = self.table(page, ("id", "name", "department", "encoding"),
                                 ("ID", "Name", "Department", "Encodings"))

    def build_records(self):
        page = self.pages["Attendance Records"]
        self.heading(page, "Attendance Records", "Filter daily attendance or export the current results.")
        filters = tk.Frame(page, bg=BG)
        filters.pack(fill="x", pady=(0, 10))
        for column, (title, variable, width) in enumerate(
            (("From (YYYY-MM-DD)", self.start, 15), ("To (YYYY-MM-DD)", self.end, 15),
             ("Person ID", self.person, 14))
        ):
            self.label(filters, title, size=9, color=MUTED).grid(row=0, column=column, sticky="w")
            field = ttk.Entry(filters, textvariable=variable, width=width)
            field.grid(row=1, column=column, sticky="ew", padx=(0, 8))
            field.bind("<Return>", lambda _: self.refresh())
        ttk.Button(filters, text="Apply", command=self.refresh).grid(row=1, column=3, padx=(0, 6))
        ttk.Button(filters, text="Reset", command=self.reset_filters).grid(row=1, column=4)
        filters.columnconfigure(5, weight=1)
        ttk.Button(filters, text="Export report", command=self.export,
                   style="Primary.TButton").grid(row=1, column=6)
        self.label(page, variable=self.record_state, color=MUTED).pack(anchor="w", pady=(0, 8))

        tabs = ttk.Notebook(page)
        tabs.pack(fill="both", expand=True)
        daily, totals = (tk.Frame(tabs, bg=BG) for _ in range(2))
        tabs.add(daily, text="Daily records")
        tabs.add(totals, text="Attendance summary")
        self.records = self.table(daily, COLUMNS, ("ID", "Name", "Date", "Time", "Status"))
        self.summary = self.table(totals, ("id", "name", "present", "days", "percent"),
                                  ("ID", "Name", "Present days", "Calendar days", "Attendance %"))

    def build_settings(self):
        page = self.pages["Settings"]
        self.heading(page, "Settings", "Choose the webcam and face recognition backend.")
        camera = self.card(page)
        camera.pack(fill="x", pady=(0, 14))
        self.label(camera, "Webcam", size=14, bold=True).pack(anchor="w")
        self.label(camera, "Camera index (usually 0)", color=MUTED).pack(anchor="w", pady=(6, 2))
        field = ttk.Entry(camera, textvariable=self.camera, width=8)
        field.pack(anchor="w")
        self.settings_inputs.append((field, "normal"))
        self.label(camera, variable=self.camera_state, color=MUTED).pack(anchor="w", pady=8)
        self.action(camera, "Check camera", self.check_camera).pack(anchor="w")

        model = self.card(page)
        model.pack(fill="x")
        self.label(model, "Face encodings", size=14, bold=True).pack(anchor="w")
        self.label(model, "Recognition backend", color=MUTED).pack(anchor="w", pady=(6, 2))
        field = ttk.Combobox(model, textvariable=self.backend, values=("opencv", "dlib"),
                             width=14, state="readonly")
        field.pack(anchor="w")
        self.settings_inputs.append((field, "readonly"))
        self.label(model, variable=self.model_state, color=MUTED).pack(anchor="w", pady=8)
        self.train_button = self.action(model, "Generate encodings", self.start_training, primary=True)
        self.train_button.pack(anchor="w")

    def table(self, frame, columns, headings):
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        tree.tag_configure("alternate", background="#f3f6fc")
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading, anchor="w")
            tree.column(column, width=170 if column in ("name", "department") else 100,
                        minwidth=64, anchor="e" if column in ("present", "days", "percent") else "w")
        return tree

    @staticmethod
    def fill_table(tree, rows):
        tree.delete(*tree.get_children())
        for index, values in enumerate(rows):
            tree.insert("", "end", values=values, tags=("alternate",) if index % 2 else ())

    def reset_filters(self):
        self.start.set(self.default_start())
        self.end.set(date.today().isoformat())
        self.person.set("")
        self.refresh()

    def refresh(self, announce=True):
        try:
            self.users = self.db.get_users()
            today = date.today().isoformat()
            attendance = self.db.get_attendance(limit=5)
            latest = attendance[0] if attendance else None
            self.metrics[0].set(str(len(self.users)))
            self.metrics[1].set(str(len(self.db.get_attendance(date=today))))
            self.metrics[2].set(f"{latest['date']}  {latest['time'][:5]}" if latest else "No records yet")
            self.fill_table(self.recent, ((row["student_id"], row["name"], row["date"],
                                          row["time"][:5], row["status"]) for row in attendance))
            self.recent_empty.place_forget()
            if not attendance:
                self.recent_empty.place(relx=0.5, rely=0.65, anchor="center")
            self.refresh_readiness()
            self.apply_filters(
                (self.start.get(), self.end.get(), self.person.get()) if announce else self.applied_filters
            )
            if announce:
                self.status.set(self.record_state.get())
        except Exception as error:
            self.error(error)

    def apply_filters(self, filters):
        records, summary = report_data(self.db, *filters)
        self.applied_filters = filters
        self.applied_report = records, summary
        display = records.copy()
        display["time"] = display["time"].str.slice(stop=5)
        self.fill_table(self.records, display.itertuples(index=False, name=None))
        self.fill_table(self.summary, summary.itertuples(index=False, name=None))
        count = len(records)
        self.record_state.set(f"{count} records shown" if count else "No attendance matches these filters.")

    def refresh_readiness(self):
        self.encoded_ids.clear()
        user_ids = {row["student_id"] for row in self.users}
        backend = self.backend.get()
        if self.demo:
            state = "Demo data only. Face encodings are not used."
        elif not user_ids:
            state = "Register a person to begin."
        elif not index_path(backend).is_file():
            state = "Generate encodings in Settings."
        else:
            try:
                _, ids = load_index(backend)
                self.encoded_ids = user_ids.intersection(ids)
                missing = len(user_ids - self.encoded_ids)
                state = (f"{missing} people need usable encodings. Check samples and regenerate."
                         if missing else f"Encodings ready for {len(user_ids)} people.")
            except (OSError, ValueError, KeyError):
                state = "Could not read encodings. Generate a fresh index in Settings."
        self.model_state.set(state)
        self.people_state.set("Fictional demo records" if self.demo else
                              f"{len(self.users)} registered" if self.users else "No people enrolled yet.")
        self.fill_table(self.people, (
            (row["student_id"], row["name"], row["department"],
             "Demo" if self.demo else "Ready" if row["student_id"] in self.encoded_ids else "Needs encoding")
            for row in self.users
        ))
        self.update_controls()

    def settings_changed(self, *_):
        self.refresh_readiness()

    def camera_changed(self, *_):
        self.camera_state.set("Camera not checked")

    def update_controls(self):
        enabled = not (self.busy or self.demo)
        for button in self.action_buttons:
            button.configure(state="normal" if enabled else "disabled")
        for field, mode in self.settings_inputs:
            field.configure(state=mode if enabled else "disabled")
        if not self.encoded_ids:
            self.start_button.configure(state="disabled")
        if not getattr(self, "users", ()):
            self.train_button.configure(state="disabled")
        self.stop_button.configure(state="normal" if self.busy else "disabled")

    def check_camera(self):
        try:
            _, index = self.settings()
        except ValueError as error:
            self.error(error)
            return

        def task():
            with webcam(index, "Camera check") as device:
                height, width = read_frame(device).shape[:2]
            return f"Camera {index} ready ({width} x {height})"

        self.run_task("Checking camera...", task, camera_check=True)

    def export(self):
        try:
            records, summary = self.applied_report
            file_type = tk.StringVar(value="Excel workbook")
            REPORTS.mkdir(parents=True, exist_ok=True)
            chosen = filedialog.asksaveasfilename(
                parent=self.root, initialdir=REPORTS,
                initialfile=f"attendance_{date.today()}", typevariable=file_type,
                filetypes=[("Excel workbook", "*.xlsx"), ("CSV file", "*.csv")],
            )
            if chosen:
                target = Path(chosen)
                if not target.suffix:
                    target = target.with_suffix(".csv" if file_type.get() == "CSV file" else ".xlsx")
                export_report(target, records, summary)
                self.status.set(f"Exported {len(records)} records to {target.name}")
        except Exception as error:
            self.error(error)

    def enrollment_dialog(self):
        dialog = tk.Toplevel(self.root, bg=BG, padx=18, pady=16)
        dialog.title("Register Person")
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
                saved = register(self.db, Vision(backend), camera, self.stop, *values,
                                 progress=self.progress)
                return "Registration saved. Generate encodings in Settings." if saved else "Registration cancelled."

            self.run_task("Opening enrollment camera...", task)

        ttk.Button(dialog, text="Cancel", command=dialog.destroy).grid(row=4, column=0, sticky="w")
        ttk.Button(dialog, text="Start capture", command=submit,
                   style="Primary.TButton").grid(row=4, column=1, sticky="e")
        for field in entries:
            field.bind("<Return>", lambda _: submit())
        dialog.bind("<Escape>", lambda _: dialog.destroy())

    def settings(self):
        try:
            camera = int(self.camera.get())
        except ValueError:
            raise ValueError("Enter a whole number for the camera index.") from None
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
            def task():
                return recognize(self.db, Vision(backend), camera, self.stop, self.progress)

            self.run_task("Starting attendance camera...", task)
        except ValueError as error:
            self.error(error)

    def run_task(self, message, task, *, camera_check=False):
        if self.busy or self.demo:
            return
        self.busy = True
        self.stop.clear()
        self.status.set(message)
        self.camera_check = camera_check
        self.update_controls()

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
                self.update_controls()
                if self.camera_check:
                    camera_state = (message if kind == "done" else
                                    "Camera unavailable. Check settings and retry.")
                    self.camera_state.set(camera_state)
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
