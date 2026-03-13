"""Windows desktop GUI for ApplyPilot."""

from __future__ import annotations

import platform
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from applypilot.gui_support import (
    build_run_command,
    build_stage_command,
    copy_resume_into_workspace,
    docx_to_pdf,
    docx_to_text,
    get_status_summary,
    load_profile_form_data,
    load_search_form_data,
    run_command,
    save_profile_form_data,
    save_search_form_data,
)
from applypilot.view import open_dashboard


PROFILE_FIELDS = [
    ("full_name", "Full name"),
    ("preferred_name", "Preferred name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("city", "City"),
    ("province_state", "State / Province"),
    ("country", "Country"),
    ("postal_code", "Postal / ZIP"),
    ("linkedin_url", "LinkedIn URL"),
    ("github_url", "GitHub URL"),
    ("current_title", "Current title"),
    ("target_role", "Target role"),
    ("years_of_experience_total", "Years of experience"),
    ("education_level", "Education level"),
    ("salary_expectation", "Salary expectation"),
    ("salary_currency", "Salary currency"),
    ("salary_range_min", "Salary min"),
    ("salary_range_max", "Salary max"),
    ("programming_languages", "Programming languages"),
    ("frameworks", "Frameworks"),
    ("tools", "Tools / platforms"),
    ("preserved_companies", "Preserved companies"),
    ("preserved_projects", "Preserved projects"),
    ("preserved_school", "Preserved school"),
    ("real_metrics", "Real metrics"),
    ("earliest_start_date", "Earliest start"),
]

SEARCH_FIELDS = [
    ("location", "Search location"),
    ("distance", "Distance (miles)"),
    ("roles", "Target roles"),
]


class ApplyPilotDesktopApp(tk.Tk):
    """Basic Windows desktop shell for ApplyPilot workflows."""

    def __init__(self) -> None:
        super().__init__()
        self.title("ApplyPilot Desktop")
        self.geometry("1180x820")
        self.minsize(980, 700)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.active_process = None
        self.profile_vars: dict[str, tk.StringVar] = {}
        self.search_vars: dict[str, tk.StringVar] = {}
        self.resume_source_var = tk.StringVar()
        self.status_message_var = tk.StringVar(value="Ready")
        self.current_action_var = tk.StringVar(value="Idle")
        self._action_buttons: list[ttk.Button] = []

        self._build_ui()
        self._load_form_defaults()
        self._refresh_status()
        self.after(150, self._drain_log_queue)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        setup_tab = ttk.Frame(notebook, padding=10)
        pipeline_tab = ttk.Frame(notebook, padding=10)
        status_tab = ttk.Frame(notebook, padding=10)
        notebook.add(setup_tab, text="Setup")
        notebook.add(pipeline_tab, text="Pipeline")
        notebook.add(status_tab, text="Status")

        self._build_setup_tab(setup_tab)
        self._build_pipeline_tab(pipeline_tab)
        self._build_status_tab(status_tab)

    def _build_setup_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Guided setup and resume tools", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.status_message_var).pack(anchor="w", pady=(4, 0))

        body = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)

        form_canvas = tk.Canvas(left, highlightthickness=0)
        form_scroll = ttk.Scrollbar(left, orient="vertical", command=form_canvas.yview)
        form_inner = ttk.Frame(form_canvas)
        form_inner.bind(
            "<Configure>",
            lambda _event: form_canvas.configure(scrollregion=form_canvas.bbox("all")),
        )
        form_canvas.create_window((0, 0), window=form_inner, anchor="nw")
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_canvas.pack(side="left", fill="both", expand=True)
        form_scroll.pack(side="right", fill="y")

        profile_box = ttk.LabelFrame(form_inner, text="Profile")
        profile_box.pack(fill="x", expand=True, pady=(0, 10))
        for row, (key, label) in enumerate(PROFILE_FIELDS):
            ttk.Label(profile_box, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.StringVar()
            ttk.Entry(profile_box, textvariable=var, width=48).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            self.profile_vars[key] = var
        profile_box.columnconfigure(1, weight=1)

        search_box = ttk.LabelFrame(form_inner, text="Search config")
        search_box.pack(fill="x", expand=True, pady=(0, 10))
        for row, (key, label) in enumerate(SEARCH_FIELDS):
            ttk.Label(search_box, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.StringVar()
            ttk.Entry(search_box, textvariable=var, width=48).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            self.search_vars[key] = var
        search_box.columnconfigure(1, weight=1)

        save_row = ttk.Frame(form_inner)
        save_row.pack(fill="x")
        ttk.Button(save_row, text="Reload Saved Config", command=self._load_form_defaults).pack(side="left")
        ttk.Button(save_row, text="Save Setup", command=self._save_setup).pack(side="left", padx=8)

        resume_box = ttk.LabelFrame(right, text="Resume tools")
        resume_box.pack(fill="x", pady=(0, 10))
        ttk.Label(resume_box, text="Resume source file").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(resume_box, textvariable=self.resume_source_var, width=46).grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(resume_box, text="Browse", command=self._browse_resume_source).grid(row=1, column=1, padx=6, pady=4)
        ttk.Button(resume_box, text="Copy TXT/PDF Into ApplyPilot", command=self._copy_resume_asset).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=4
        )
        ttk.Button(resume_box, text="Convert DOCX -> TXT", command=self._convert_docx_to_text).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=4
        )
        ttk.Button(resume_box, text="Convert DOCX -> PDF", command=self._convert_docx_to_pdf).grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=6, pady=4
        )
        resume_box.columnconfigure(0, weight=1)

        notes = ttk.LabelFrame(right, text="Notes")
        notes.pack(fill="both", expand=True)
        ttk.Label(
            notes,
            justify="left",
            wraplength=320,
            text=(
                "Use Setup to edit your saved ApplyPilot profile and search config.\n\n"
                "For resume tools, browse to a local .docx, .txt, or .pdf file. "
                "DOCX conversion writes outputs next to the source file."
            ),
        ).pack(anchor="w", padx=8, pady=8)

    def _build_pipeline_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Run stages from the desktop", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.current_action_var).pack(anchor="w", pady=(4, 0))

        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=(0, 10))

        actions = [
            ("Discover", lambda: self._start_command(build_stage_command("discover"), "Discover")),
            ("Enrich", lambda: self._start_command(build_stage_command("enrich"), "Enrich")),
            ("Score", lambda: self._start_command(build_stage_command("score"), "Score")),
            ("Tailor", lambda: self._start_command(build_stage_command("tailor"), "Tailor")),
            ("Cover", lambda: self._start_command(build_stage_command("cover"), "Cover")),
            ("PDF", lambda: self._start_command(build_stage_command("pdf"), "PDF")),
            ("Run All", lambda: self._start_command(build_run_command(), "Run All")),
            ("Apply", lambda: self._start_command(build_stage_command("apply"), "Apply")),
        ]
        for idx, (label, command) in enumerate(actions):
            btn = ttk.Button(button_frame, text=label, command=command)
            btn.grid(row=0, column=idx, padx=4, pady=4, sticky="ew")
            button_frame.columnconfigure(idx, weight=1)
            self._action_buttons.append(btn)

        self.log_text = ScrolledText(parent, wrap="word", height=32, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _build_status_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Refresh Status", command=self._refresh_status).pack(side="left")
        ttk.Button(top, text="Open HTML Dashboard", command=self._open_dashboard).pack(side="left", padx=8)

        self.status_text = ScrolledText(parent, wrap="word", height=36, font=("Consolas", 10))
        self.status_text.pack(fill="both", expand=True)
        self.status_text.configure(state="disabled")

    def _load_form_defaults(self) -> None:
        profile = load_profile_form_data()
        search = load_search_form_data()
        for key, var in self.profile_vars.items():
            var.set(profile.get(key, ""))
        for key, var in self.search_vars.items():
            var.set(search.get(key, ""))
        self.status_message_var.set("Loaded saved setup values.")

    def _save_setup(self) -> None:
        save_profile_form_data({key: var.get() for key, var in self.profile_vars.items()})
        save_search_form_data({key: var.get() for key, var in self.search_vars.items()})
        self.status_message_var.set("Saved profile and search config.")
        self._refresh_status()

    def _browse_resume_source(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a resume file",
            filetypes=[
                ("Resume files", "*.docx *.txt *.pdf"),
                ("Word Documents", "*.docx"),
                ("Text Files", "*.txt"),
                ("PDF Files", "*.pdf"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.resume_source_var.set(path)

    def _require_resume_source(self) -> Path:
        source = self.resume_source_var.get().strip()
        if not source:
            raise ValueError("Select a resume source file first.")
        return Path(source)

    def _copy_resume_asset(self) -> None:
        try:
            saved = copy_resume_into_workspace(self._require_resume_source())
        except Exception as exc:
            messagebox.showerror("Resume copy failed", str(exc))
            return
        self.status_message_var.set(f"Copied resume to {saved}")
        self._refresh_status()

    def _convert_docx_to_text(self) -> None:
        try:
            source = self._require_resume_source()
            if source.suffix.lower() != ".docx":
                raise ValueError("Choose a .docx file for conversion.")
            out = docx_to_text(source)
        except Exception as exc:
            messagebox.showerror("DOCX to TXT failed", str(exc))
            return
        self.status_message_var.set(f"Wrote text resume to {out}")
        self.log_queue.put(f"[resume] DOCX -> TXT: {out}\n")

    def _convert_docx_to_pdf(self) -> None:
        try:
            source = self._require_resume_source()
            if source.suffix.lower() != ".docx":
                raise ValueError("Choose a .docx file for conversion.")
            out = docx_to_pdf(source)
        except Exception as exc:
            messagebox.showerror("DOCX to PDF failed", str(exc))
            return
        self.status_message_var.set(f"Wrote PDF resume to {out}")
        self.log_queue.put(f"[resume] DOCX -> PDF: {out}\n")

    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for btn in self._action_buttons:
            btn.configure(state=state)

    def _start_command(self, command: list[str], label: str) -> None:
        if self.active_process is not None:
            messagebox.showinfo("ApplyPilot", "A command is already running.")
            return

        self.current_action_var.set(f"Running: {label}")
        self._set_actions_enabled(False)
        self._append_log(f"\n== {label} ==\n$ {' '.join(command)}\n")

        def worker() -> None:
            try:
                proc = run_command(command, cwd=Path.cwd())
                self.active_process = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.log_queue.put(line)
                exit_code = proc.wait()
                self.log_queue.put(f"\n[exit] code={exit_code}\n")
            except Exception as exc:
                self.log_queue.put(f"\n[error] {exc}\n")
            finally:
                self.active_process = None
                self.log_queue.put("__PROCESS_DONE__")

        threading.Thread(target=worker, daemon=True).start()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__PROCESS_DONE__":
                self.current_action_var.set("Idle")
                self._set_actions_enabled(True)
                self._refresh_status()
                continue
            self._append_log(item)
        self.after(150, self._drain_log_queue)

    def _refresh_status(self) -> None:
        summary = get_status_summary()
        stats = summary["stats"]
        lines = [
            f"App dir: {summary['app_dir']}",
            f"Tier: {summary['tier']}",
            "",
            f"profile.json: {summary['profile_exists']}",
            f"resume.txt:  {summary['resume_txt_exists']}",
            f"resume.pdf:  {summary['resume_pdf_exists']}",
            f"searches.yaml: {summary['search_exists']}",
            f".env: {summary['env_exists']}",
            "",
            f"Total jobs: {stats['total']}",
            f"With description: {stats['with_description']}",
            f"Scored: {stats['scored']}",
            f"Tailored: {stats['tailored']}",
            f"Cover letters: {stats['with_cover_letter']}",
            f"Ready to apply: {stats['ready_to_apply']}",
            f"Applied: {stats['applied']}",
            "",
            "Pending by stage:",
            f"  enrich: {stats['pending_by_stage']['enrich']}",
            f"  score: {stats['pending_by_stage']['score']}",
            f"  tailor: {stats['pending_by_stage']['tailor']}",
            f"  cover: {stats['pending_by_stage']['cover']}",
            f"  pdf: {stats['pending_by_stage']['pdf']}",
            f"  apply: {stats['pending_by_stage']['apply']}",
            "",
            f"Next stage: {stats['next_stage_to_run']}",
        ]
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", "\n".join(lines))
        self.status_text.configure(state="disabled")

    def _open_dashboard(self) -> None:
        try:
            open_dashboard()
        except Exception as exc:
            messagebox.showerror("Dashboard", str(exc))


def launch_gui() -> None:
    """Launch the desktop GUI."""
    if platform.system() != "Windows":
        raise SystemExit("The desktop GUI is Windows-only in this version.")
    app = ApplyPilotDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
