from __future__ import annotations

import contextlib
import hashlib
import io
import json
import threading
import urllib.parse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from scheduled_api_runner import RunnerError, ScheduledRunner
from guided_config import GuidedConfigError, make_get_job, add_daily_csv_output, add_auth_header_env, save_new_config
from api_data_panel import ApiDataExplorerPanel
from scheduler_windows_tasks import (
    WindowsTaskError, register_task, unregister_task, validate_dated_get_config, run_locked_config
)
from ui_language import load_language, save_language

APP_ID = "scheduled-api-runner"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ScheduledApiDesktop:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.lang = load_language(APP_ID)
        self.root.geometry("1080x760")
        self.root.minsize(900, 640)
        self.config_path = tk.StringVar()
        self.guide_root = tk.StringVar()
        self.guide_name = tk.StringVar(value="Daily API data")
        self.guide_url = tk.StringVar(value="https://example.com/api/data")
        self.guide_at = tk.StringVar(value="09:00")
        self.guide_csv_enabled = tk.BooleanVar(value=True)
        self.guide_csv_path = tk.StringVar(value="daily-sales.csv")
        self.guide_csv_fields = tk.StringVar(value="sales = data.sales")
        self.guide_csv_date_path = tk.StringVar(value="")
        self.guide_auth_header = tk.StringVar(value="")
        self.guide_auth_env = tk.StringVar(value="")
        self.status = tk.StringVar(value="")
        self.config: dict | None = None
        self.monitor_thread: threading.Thread | None = None
        self._once_running = False
        self._task_busy = False
        self.preview_revision: str | None = None
        self.stop_event = threading.Event()
        self._build()
        default = Path(__file__).resolve().parent / "jobs.example.json"
        if default.is_file():
            self.config_path.set(str(default))
            self._load_config(False)
        else:
            self.status.set(self.t("準備完了", "Ready"))

    def t(self, ja: str, en: str) -> str:
        return en if self.lang == "en" else ja

    def _build(self) -> None:
        saved_explorer = (self.explorer.sources_snapshot()
                          if getattr(self, 'explorer', None) is not None else None)
        for child in self.root.winfo_children():
            child.destroy()
        self.root.title(self.t("定期API実行", "Scheduled API Runner"))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)
        self.explorer_tab = ttk.Frame(self.notebook)
        self.guide_tab = ttk.Frame(self.notebook)
        self.advanced_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.guide_tab, text=self.t("① 毎日CSV取得の設定", "1. Daily CSV setup"))
        self.notebook.add(self.explorer_tab, text=self.t("② API項目を調べる", "2. Inspect API fields"))
        self.notebook.add(self.advanced_tab, text=self.t("③ 試運転・実行", "3. Preview / Run"))
        self.explorer = ApiDataExplorerPanel(
            self.explorer_tab, japanese=self.lang == 'ja', initial_sources=saved_explorer,
            on_schedule_source=self._use_explorer_source)
        self.explorer.pack(fill='both', expand=True)
        self._build_guide()
        outer = ttk.Frame(self.advanced_tab, padding=18)
        outer.pack(fill="both", expand=True)

        language = ttk.Frame(outer)
        language.pack(fill="x", pady=(0, 8))
        ttk.Label(language, text="言語 / Language", font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 6))
        self.language_var = tk.StringVar(value="日本語" if self.lang == "ja" else "English")
        combo = ttk.Combobox(language, textvariable=self.language_var, values=("日本語", "English"), state="readonly", width=10)
        combo.pack(side="right")
        combo.bind("<<ComboboxSelected>>", self._language_changed)

        ttk.Label(outer, text=self.t("定期API実行", "Scheduled API Runner"), font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text=self.t(
                "使い方：①設定JSONを選ぶ → ②検証・試運転（外部送信なし）→ ③内容を確認して1回実行、または定期実行。許可したHTTPSホストのみ通信します。",
                "Start here: 1. Select JSON → 2. Validate and Dry Run (no API requests) → 3. Confirm and run once or schedule. HTTPS allowlisted hosts only.",
            ),
            wraplength=940,
        ).pack(anchor="w", pady=(0, 14))

        cfg = ttk.LabelFrame(outer, text=self.t("設定", "Configuration"), padding=10)
        cfg.pack(fill="x", pady=(0, 10))
        ttk.Entry(cfg, textvariable=self.config_path).pack(side="left", fill="x", expand=True)
        ttk.Button(cfg, text=self.t("選択", "Browse"), command=self._browse).pack(side="left", padx=(8, 0))
        ttk.Button(cfg, text=self.t("検証", "Validate"), command=lambda: self._load_config(True)).pack(side="left", padx=(6, 0))

        info = ttk.LabelFrame(outer, text=self.t("ジョブ概要", "Jobs"), padding=8)
        info.pack(fill="both", expand=True, pady=(0, 10))
        cols = ("name", "schedule", "method", "host", "enabled")
        self.jobs = ttk.Treeview(info, columns=cols, show="headings", height=8)
        labels = (
            self.t("名前", "Name"), self.t("スケジュール", "Schedule"), "Method",
            self.t("Host（秘密値なし）", "Host (secret-free)"), self.t("有効", "Enabled"),
        )
        widths = (200, 210, 90, 330, 80)
        for col, label, width in zip(cols, labels, widths):
            self.jobs.heading(col, text=label)
            self.jobs.column(col, width=width, anchor="w")
        self.jobs.pack(fill="both", expand=True)
        self.host_label = ttk.Label(info, text="")
        self.host_label.pack(anchor="w", pady=(8, 0))

        actions = ttk.LabelFrame(outer, text=self.t("実行", "Execution"), padding=10)
        actions.pack(fill="x", pady=(0, 10))
        self.dry_btn = ttk.Button(actions, text=self.t("全ジョブ確認（Dry Run）", "Dry Run All"), command=self._dry_run)
        self.dry_btn.pack(side="left")
        self.run_btn = ttk.Button(actions, text=self.t("有効ジョブを1回実行", "Run Enabled Once"), command=self._live_once)
        self.run_btn.pack(side="left", padx=6)
        self.start_btn = ttk.Button(actions, text=self.t("定期実行開始", "Start Scheduler"), command=self._start_scheduler)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text=self.t("停止", "Stop"), command=self._stop_scheduler, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Label(
            actions,
            text=self.t(
                "Live実行は外部APIへ実際に送信します。先にDry Runを実行してください。",
                "Live execution sends real requests to external APIs. Run Dry Run first.",
            ),
            wraplength=410,
        ).pack(side="right")

        task_box = ttk.LabelFrame(outer, text=self.t(
            "Windowsの毎日自動実行（任意）", "Optional Windows daily task"), padding=8)
        task_box.pack(fill="x", pady=(0, 9))
        self.task_register_btn = ttk.Button(
            task_box, text=self.t("Windowsタスクを登録", "Register daily Windows task"),
            command=self._register_windows_task)
        self.task_register_btn.pack(side="left", padx=(0, 8))
        self.task_remove_btn = ttk.Button(
            task_box, text=self.t("登録したタスクを削除", "Remove registered task"),
            command=self._remove_windows_task)
        self.task_remove_btn.pack(side="left", padx=(0, 8))
        ttk.Label(task_box, text=self.t(
            "毎日GET＋CSVのみ。ログオン中に実行。設定変更後は再登録。",
            "GET+CSV only; runs while signed in. Re-register after config changes."),
            wraplength=430).pack(side="left")
        if self._task_busy:
            self.task_register_btn.configure(state="disabled")
            self.task_remove_btn.configure(state="disabled")
        logbox = ttk.LabelFrame(outer, text=self.t("実行表示", "Audit view"), padding=8)
        logbox.pack(fill="both", expand=True)
        self.log = tk.Text(logbox, wrap="word", height=13, state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(logbox, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(outer, textvariable=self.status).pack(fill="x", pady=(8, 0))

        if self.monitor_thread is not None or self._once_running:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal" if self.monitor_thread is not None else "disabled")
            self.run_btn.configure(state="disabled")
            self.dry_btn.configure(state="disabled")

    def _build_guide(self) -> None:
        # Long onboarding form remains usable on laptop displays and at 150% DPI.
        canvas = tk.Canvas(self.guide_tab, highlightthickness=0)
        scroll = ttk.Scrollbar(self.guide_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        pane = ttk.Frame(canvas, padding=20)
        form_window = canvas.create_window((0, 0), window=pane, anchor="nw")
        pane.bind("<Configure>", lambda _event: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(
            form_window, width=event.width))
        banner = ttk.Frame(pane)
        banner.pack(fill="x", pady=(0, 10))
        ttk.Label(banner, text=self.t("定期API実行とは？", "What does Scheduled API Runner do?"),
                  font=("Segoe UI", 18, "bold")).pack(side="left")
        guide_lang = ttk.Combobox(
            banner, values=("日本語", "English"), state="readonly", width=10
        )
        guide_lang.set("English" if self.lang == "en" else "日本語")
        self.guide_language = guide_lang
        guide_lang.pack(side="right")
        guide_lang.bind("<<ComboboxSelected>>", self._guide_language_changed)
        ttk.Label(pane, text=self.t(
            "APIから今日の数値を取得し、昨日までのCSVデータに日付ごとに追記します。\n"
            "使い方：①保存先・API URL・JSON項目・時刻を指定 → ②必要ならAPI項目を調べる "
            "→ ③設定を保存 → ④試運転 → ⑤承認して実行またはWindowsタスク登録。",
            "Fetch daily API values and append one dated row to your existing CSV history.\n"
            "1. Set destination, HTTPS URL, JSON fields and time. 2. Inspect API fields if needed. "
            "3. Save. 4. Dry Run. 5. Approve live execution or optional Windows task.",
        ), wraplength=880, justify="left").pack(anchor="w", pady=(0, 16))
        group = ttk.LabelFrame(pane, text=self.t("① API取得とCSV履歴を設定", "1. API and CSV history setup"), padding=12)
        group.pack(fill="x", pady=(0, 12))
        group.columnconfigure(1, weight=1)
        fields = [
            (self.t("作業用フォルダー", "Local work folder"), self.guide_root),
            (self.t("ジョブ名", "Job name"), self.guide_name),
            (self.t("HTTPS URL", "HTTPS URL"), self.guide_url),
            (self.t("毎日の実行時刻 (HH:MM)", "Daily time (HH:MM)"), self.guide_at),
        ]
        for i, (label, variable) in enumerate(fields):
            ttk.Label(group, text=label).grid(row=i, column=0, sticky="w", pady=6, padx=(0, 10))
            ttk.Entry(group, textvariable=variable).grid(row=i, column=1, sticky="ew", pady=6)
        ttk.Button(group, text=self.t("選択…", "Browse…"), command=self._choose_guide_root).grid(
            row=0, column=2, padx=(8, 0))
        ttk.Checkbutton(group, variable=self.guide_csv_enabled, text=self.t(
            "取得したJSONの値を日付付きCSVに追記（初期ON）",
            "Append extracted API values into dated CSV (on by default)")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(7, 2))
        ttk.Label(group, text=self.t(
            "CSVファイル名（例 daily-sales.csv）", "CSV filename (e.g. daily-sales.csv)")
        ).grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(group, textvariable=self.guide_csv_path).grid(
            row=5, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Label(group, text=self.t(
            "JSON項目（1行に1項目。例 sales = data.sales）",
            "JSON fields (one per line, e.g. sales = data.sales)")
        ).grid(row=6, column=0, sticky="nw", padx=(0, 10), pady=4)
        self.guide_fields_editor = tk.Text(group, height=4, wrap="none")
        self.guide_fields_editor.insert("1.0", self.guide_csv_fields.get())
        self.guide_fields_editor.grid(row=6, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Label(group, text=self.t(
            "APIの日付項目（任意）", "API date path (optional)")
        ).grid(row=7, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(group, textvariable=self.guide_csv_date_path).grid(
            row=7, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Label(group, text=self.t(
            "API内に日付がある場合は data.date などを指定。空欄ならPCの実行日を記録。"
            "同じ日付はスキップ。更新時は元CSVのバックアップを保持します。",
            "Set e.g. data.date when the API includes a date; otherwise use PC run date. "
            "Duplicate dates are skipped and original CSV is backed up before updates."),
            wraplength=780).grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 6))
        ttk.Label(group, text=self.t(
            "認証ヘッダー名（任意、例 X-API-Key）",
            "Authentication header (optional, e.g. X-API-Key)")).grid(row=9, column=0, sticky="w", pady=4)
        ttk.Entry(group, textvariable=self.guide_auth_header).grid(row=9, column=1, sticky="ew", pady=4)
        ttk.Label(group, text=self.t(
            "Windows環境変数の名前（例 MY_SALES_API_KEY）",
            "Windows environment variable name (e.g. MY_SALES_API_KEY)")).grid(row=10, column=0, sticky="w", pady=4)
        ttk.Entry(group, textvariable=self.guide_auth_env).grid(row=10, column=1, sticky="ew", pady=4)
        ttk.Label(group, text=self.t(
            "秘密のAPIキー自体は入力しません。利用者のWindows環境変数を事前に設定してください。",
            "Do not paste an API key here. Set the variable in your Windows account first."),
            wraplength=820).grid(row=11, column=0, columnspan=3, sticky="w", pady=5)
        ttk.Label(pane, text=self.t(
            "② 設定を新規保存するだけではAPIへの通信は発生しません.保存後の画面で試運転を実行してください。\n"
            "③ 試運転後に実行を承認します。アプリを閉じたい場合は、ログオン中のWindowsタスクとして登録できます。",
            "2. Saving a config sends no requests. Complete Dry Run on the next tab.\n"
            "3. Approve live execution, or register a daily Windows task to run while signed in.",
        ), wraplength=870, justify="left").pack(anchor="w", pady=(6, 12))
        ttk.Button(pane, text=self.t("設定JSONを新規保存して次へ →", "Save new config and continue →"),
                   command=self._create_guided_config).pack(anchor="w", pady=(0, 10))
        ttk.Button(pane, text=self.t("既存JSONを使う（詳細画面へ）", "Use existing JSON (advanced)"),
                   command=lambda: self.notebook.select(self.advanced_tab)).pack(anchor="w")
        ttk.Label(pane, text=self.t(
            "注意：この画面はGET専用です。APIキー等の秘密情報はURLやジョブ名に入力せず、\n"
            "詳細設定で環境変数による管理を使用してください。",
            "Note: GET-only wizard. Do not put API keys or secrets in URLs or names.\n"
            "Advanced JSON supports environment-variable references for credentials.",
        ), wraplength=870, justify="left").pack(anchor="w", pady=(14, 0))

    def _use_explorer_source(self, source: dict) -> None:
        """Bring a manually inspected API's selected JSON fields into daily setup."""
        if self._once_running or self.monitor_thread is not None or self._task_busy:
            return
        if "[*]" in source["fields"]:
            messagebox.showwarning(
                self.t("日次データは1行です", "Daily data is one observation"),
                self.t("配列[*]を扱う画面は手動取得用です。毎日CSV履歴では1項目に1つの値だけ指定してください。",
                       "The daily CSV updater expects one scalar per field. Remove [*] array selectors."),
                parent=self.root)
            return
        self.guide_url.set(source["url"])
        self.guide_csv_fields.set(source["fields"])
        self.guide_fields_editor.delete("1.0", "end")
        self.guide_fields_editor.insert("1.0", source["fields"])
        self.guide_auth_header.set(source.get("header_name", ""))
        self.guide_name.set(source["name"])
        self.guide_csv_enabled.set(True)
        self.notebook.select(self.guide_tab)
        self.preview_revision = None
        self.status.set(self.t(
            "APIの項目を取り込みました。CSV名・日付項目・認証環境変数を確認して保存してください。",
            "API fields imported. Review CSV name, date path and authentication variable, then save."))

    def _guide_language_changed(self, _event=None) -> None:
        if self._once_running or self.monitor_thread is not None or self.explorer.busy:
            self.guide_language.set("English" if self.lang == "en" else "日本語")
            return
        self.guide_csv_fields.set(self.guide_fields_editor.get("1.0", "end").strip())
        self.lang = "en" if self.guide_language.get() == "English" else "ja"
        save_language(APP_ID, self.lang)
        self._build()
        if self.config is not None:
            self._render_summary(self.config)

    def _choose_guide_root(self) -> None:
        if self._once_running or self.monitor_thread is not None:
            return
        directory = filedialog.askdirectory(parent=self.root)
        if directory:
            self.guide_root.set(directory)

    def _create_guided_config(self) -> None:
        if self._once_running or self.monitor_thread is not None:
            return
        try:
            config = make_get_job(
                root_dir=self.guide_root.get(), name=self.guide_name.get(),
                url=self.guide_url.get(), daily_at=self.guide_at.get(),
            )
            if getattr(self, 'guide_csv_enabled', None) is not None and self.guide_csv_enabled.get():
                config = add_daily_csv_output(
                    config, path=self.guide_csv_path.get(),
                    fields=self.guide_fields_editor.get("1.0", "end").strip(),
                    date_path=self.guide_csv_date_path.get(), on_duplicate='skip')
            config = add_auth_header_env(
                config, header_name=self.guide_auth_header.get(),
                env_name=self.guide_auth_env.get())
        except (GuidedConfigError, OSError) as exc:
            messagebox.showerror(self.t("設定内容を確認", "Check your settings"), str(exc), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json", initialfile="api-job.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            save_new_config(path, config)
        except OSError as exc:
            messagebox.showerror(self.t("保存できませんでした", "Could not save"), str(exc), parent=self.root)
            return
        self.preview_revision = None
        self.config_path.set(str(path))
        self.notebook.select(self.advanced_tab)
        self._load_config(True)
        self.status.set(self.t("保存完了。次はDry Runです（まだAPIへ送信していません）。",
                               "Saved. Next: Dry Run (no API request has been sent)."))

    def _language_changed(self, _event=None) -> None:
        if self._once_running or self.monitor_thread is not None or self.explorer.busy:
            self.language_var.set("English" if self.lang == "en" else "日本語")
            return
        was_advanced = self.notebook.select() == str(self.advanced_tab)
        self.guide_csv_fields.set(self.guide_fields_editor.get("1.0", "end").strip())
        self.lang = "en" if self.language_var.get() == "English" else "ja"
        save_language(APP_ID, self.lang)
        self._build()
        if was_advanced:
            self.notebook.select(self.advanced_tab)
        if self.config is not None:
            self._render_summary(self.config)
        self.status.set(self.t("定期実行中", "Scheduler running") if self.monitor_thread is not None else self.t("準備完了", "Ready"))

    def _browse(self) -> None:
        if self._once_running or self.monitor_thread is not None:
            return
        path = filedialog.askopenfilename(
            title=self.t("定期API設定JSONを選択", "Choose Scheduled API JSON"),
            filetypes=[("JSON", "*.json"), (self.t("すべてのファイル", "All files"), "*.*")],
        )
        if path:
            self.config_path.set(path)
            self._load_config(True)

    def _read_raw(self) -> dict:
        path = Path(self.config_path.get()).expanduser().resolve()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RunnerError("config root must be an object")
        return raw

    def _job_summary(self, job: dict) -> tuple[str, str, str, str, str]:
        name = str(job.get("name", "unnamed"))
        schedule = job.get("schedule", {}) if isinstance(job.get("schedule", {}), dict) else {}
        schedule_type = str(schedule.get("type", "?"))
        if schedule_type == "daily":
            schedule_text = self.t(f"毎日 {schedule.get('at', '?')}", f"daily {schedule.get('at', '?')}")
        elif schedule_type == "interval":
            schedule_text = self.t(f"{schedule.get('seconds', '?')}秒ごと", f"every {schedule.get('seconds', '?')} sec")
        else:
            schedule_text = schedule_type
        request = job.get("request", {}) if isinstance(job.get("request", {}), dict) else {}
        method = str(request.get("method", "GET")).upper()
        raw_url = str(request.get("url", ""))
        try:
            parsed = urllib.parse.urlparse(raw_url)
            host = parsed.hostname or self.t("(ENV/不明)", "(ENV/unknown)")
        except Exception:
            host = self.t("(不正)", "(invalid)")
        return name, schedule_text, method, host, self.t("はい", "yes") if job.get("enabled", True) else self.t("いいえ", "no")

    def _load_config(self, show_error: bool) -> bool:
        try:
            raw = self._read_raw()
            ScheduledRunner(raw, dry_run=True)
            self.config = raw
            self._render_summary(raw)
            self.status.set(self.t("設定OK", "Configuration valid"))
            return True
        except Exception as exc:
            self.config = None
            self.status.set(self.t(f"設定エラー: {type(exc).__name__}", f"Configuration error: {type(exc).__name__}"))
            if show_error:
                messagebox.showerror(self.t("設定エラー", "Configuration error"), str(exc), parent=self.root)
            return False

    def _render_summary(self, raw: dict) -> None:
        for item in self.jobs.get_children():
            self.jobs.delete(item)
        for job in raw.get("jobs", []):
            if isinstance(job, dict):
                self.jobs.insert("", "end", values=self._job_summary(job))
        hosts = [str(x) for x in raw.get("allow_hosts", [])]
        self.host_label.configure(text=self.t("許可ホスト: ", "Allowed hosts: ") + (", ".join(hosts) if hosts else "-"))

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _capture(self, fn):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            fn()
        return buffer.getvalue()

    def _revision(self, raw: dict) -> str:
        # A different selected config file is never approved by an old preview.
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload = str(Path(self.config_path.get()).expanduser().resolve()) + "\\n" + canonical
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _preview_complete(self, ok: bool, text: str, status: str, revision: str) -> None:
        # The user may have edited the JSON while the worker was reading it.
        # Verify on disk at completion, then allow one future live execution.
        self.preview_revision = None
        if ok:
            try:
                if self._revision(self._read_raw()) == revision:
                    self.preview_revision = revision
                else:
                    status = self.t("設定変更後は再試運転してください", "Configuration changed: dry-run again")
            except (OSError, ValueError, RunnerError, json.JSONDecodeError):
                status = self.t("設定を再確認してください", "Recheck configuration")
        self._finish(ok, text, status)

    def _preview_ready(self) -> bool:
        if self.preview_revision is not None and self.config is not None:
            if self._revision(self.config) == self.preview_revision:
                return True
        messagebox.showwarning(
            self.t("試運転が必要", "Dry Run required"),
            self.t("この設定で試運転を成功させてから実行してください。",
                   "Run a successful Dry Run on this exact configuration before sending requests."),
            parent=self.root,
        )
        return False

    def _dry_run(self) -> None:
        if self._once_running or self.monitor_thread is not None or not self._load_config(True):
            return
        assert self.config is not None
        raw = self.config
        revision = self._revision(raw)
        self.preview_revision = None
        self._once_running = True
        self.run_btn.configure(state="disabled")
        self.dry_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")
        self.status.set(self.t("確認中…", "Dry Run…"))

        def worker() -> None:
            try:
                text = self._capture(lambda: ScheduledRunner(raw, dry_run=True).run_all_once())
                self.root.after(0, lambda t=text: self._preview_complete(
                    True, t or "Dry Run OK", self.t("確認完了", "Dry Run complete"), revision))
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda e=error_text: self._preview_complete(
                    False, e, self.t("確認失敗", "Dry Run failed"), revision))

        threading.Thread(target=worker, daemon=True).start()

    def _has_mutating_jobs(self) -> bool:
        if not self.config:
            return False
        for job in self.config.get("jobs", []):
            if not isinstance(job, dict) or job.get("enabled", True) is False:
                continue
            request = job.get("request", {})
            if isinstance(request, dict) and str(request.get("method", "GET")).upper() in MUTATING_METHODS:
                return True
        return False

    def _confirm_live(self, scheduled: bool) -> bool:
        risk = self.t("\nPOST/PUT/PATCH/DELETEを含む有効ジョブがあります。", "\nEnabled jobs include POST/PUT/PATCH/DELETE.") if self._has_mutating_jobs() else ""
        mode = self.t("定期実行を開始", "Start scheduled execution") if scheduled else self.t("有効ジョブを今すぐ1回実行", "Run enabled jobs once now")
        message = self.t(
            f"{mode}します。外部APIへ実際に送信されます。{risk}\n更新系リクエストは自動再送しません。手動で再実行すると再送されます。\n\nDry Runと設定確認が済んでいる場合だけ続行してください。",
            f"{mode}. Real requests will be sent to external APIs.{risk}\nMutating requests are not automatically retried; manual re-runs send them again.\n\nContinue only after Dry Run and configuration review.",
        )
        return messagebox.askyesno(self.t("実API実行", "Live API execution"), message, parent=self.root)

    def _live_once(self) -> None:
        if self._once_running or self.monitor_thread is not None or not self._load_config(True):
            return
        if not self._preview_ready() or not self._confirm_live(False):
            return
        assert self.config is not None
        raw = self.config
        # Do not retain permission if the remote API acts but the response is lost.
        self.preview_revision = None
        self._once_running = True
        self.run_btn.configure(state="disabled")
        self.dry_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")
        self.status.set(self.t("実API実行中…", "Running live requests…"))

        def worker() -> None:
            try:
                text = self._capture(lambda: ScheduledRunner(raw, dry_run=False).run_all_once())
                self.root.after(0, lambda: self._finish(True, text or "Run OK", self.t("実行完了", "Run complete")))
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda e=error_text: self._finish(
                    False, e, self.t("実行失敗", "Run failed")))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, ok: bool, text: str, status: str) -> None:
        self._once_running = False
        self._append(text)
        self.status.set(status)
        if self.monitor_thread is None:
            self.run_btn.configure(state="normal")
            self.dry_btn.configure(state="normal")
            self.start_btn.configure(state="normal")
        if not ok:
            messagebox.showerror(self.t("定期API実行", "Scheduled API Runner"), text[-1500:], parent=self.root)

    def _task_complete(self, ok: bool, operation: str, detail: str) -> None:
        self._task_busy = False
        self.task_register_btn.configure(state="normal")
        self.task_remove_btn.configure(state="normal")
        self.status.set(self.t("Windowsタスク処理完了" if ok else "Windowsタスク処理失敗",
                               "Windows task updated" if ok else "Windows task operation failed"))
        if ok:
            messagebox.showinfo(self.t("Windowsタスク", "Windows Task"), detail, parent=self.root)
        else:
            messagebox.showerror(self.t("Windowsタスク", "Windows Task"), detail, parent=self.root)

    def _task_worker(self, operation: str, path: Path, digest: str = "") -> None:
        self._task_busy = True
        self.task_register_btn.configure(state="disabled")
        self.task_remove_btn.configure(state="disabled")
        self.status.set(self.t("Windowsのタスクを設定中…", "Configuring Windows Task Scheduler…"))

        def work():
            try:
                result = register_task(path, expected_sha256=digest) if operation == "add" else unregister_task(path)
                ok, detail = True, self.t("操作成功：", "Task updated: ") + result
            except (WindowsTaskError, OSError, ValueError) as exc:
                ok, detail = False, str(exc)
            self.root.after(0, lambda: self._task_complete(ok, operation, detail))
        threading.Thread(target=work, daemon=True).start()

    def _register_windows_task(self) -> None:
        if self._once_running or self.monitor_thread is not None or self._task_busy:
            return
        if not self._load_config(True) or not self._preview_ready():
            return
        assert self.config is not None
        try:
            when = validate_dated_get_config(self.config)
            path = Path(self.config_path.get()).expanduser().resolve()
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        except (WindowsTaskError, ValueError, OSError) as exc:
            messagebox.showerror(self.t("登録条件", "Task requirements"), str(exc), parent=self.root)
            return
        if not messagebox.askyesno(self.t("毎日のAPI取得を登録", "Register daily API task"),
                self.t(f"毎日{when}にこのGET API設定をWindowsに登録します。"
                       "ログオン中のみ実行。設定ファイル変更後は自動停止します。"
                       "既存の同名タスクは上書きしません。続行しますか？",
                       f"Register this GET API collection every day at {when}? "
                       "Runs while signed in. Changes to the saved JSON stop future execution. "
                       "Existing tasks will not be overwritten. Continue?"),
                parent=self.root):
            return
        self.preview_revision = None
        self._task_worker("add", path, checksum)

    def _remove_windows_task(self) -> None:
        if self._once_running or self.monitor_thread is not None or self._task_busy:
            return
        path_text = self.config_path.get()
        if not path_text:
            return
        path = Path(path_text).expanduser().resolve()
        if not messagebox.askyesno(
                self.t("Windowsタスクを削除", "Remove Windows task"),
                self.t("この設定ファイルに紐づくWindowsタスクを停止・削除しますか？"
                       "保存済みJSONとCSVファイルは削除しません。",
                       "Remove the task for this saved config? JSON and CSV files remain."),
                parent=self.root):
            return
        self._task_worker("remove", path)

    def _start_scheduler(self) -> None:
        if self._once_running or self.monitor_thread is not None or not self._load_config(True):
            return
        if not self._preview_ready() or not self._confirm_live(True):
            return
        assert self.config is not None
        raw = self.config
        self.preview_revision = None
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.run_btn.configure(state="disabled")
        self.dry_btn.configure(state="disabled")
        self.status.set(self.t("定期実行中", "Scheduler running"))

        def loop() -> None:
            try:
                runner = ScheduledRunner(raw, dry_run=False)
                while not self.stop_event.is_set():
                    text = self._capture(runner.run_due)
                    if text:
                        self.root.after(0, lambda t=text: self._append(t))
                    self.stop_event.wait(runner.poll_seconds)
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda e=error_text: messagebox.showerror(
                    self.t("スケジューラエラー", "Scheduler error"), e, parent=self.root))
            finally:
                self.root.after(0, self._scheduler_stopped)

        self.monitor_thread = threading.Thread(target=loop, daemon=True)
        self.monitor_thread.start()

    def _stop_scheduler(self) -> None:
        self.stop_event.set()
        self.status.set(self.t("停止中…", "Stopping…"))

    def _scheduler_stopped(self) -> None:
        self.monitor_thread = None
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.dry_btn.configure(state="normal")
        self.status.set(self.t("停止しました", "Stopped"))


def self_test() -> int:
    """Verify packaged imports, config generation and no-network Dry Run."""
    import tempfile
    from api_data_explorer import extract_rows, save_xlsx, validate_sources
    with tempfile.TemporaryDirectory(prefix="scheduled-api-self-test-") as d:
        test_config = make_get_job(
            root_dir=d, name="Self test GET",
            url="https://example.com/status", daily_at="09:00",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            ScheduledRunner(test_config, dry_run=True).run_all_once()
        root = Path(d)
        if (root / ".state").exists() or (root / "logs").exists():
            raise RuntimeError("Dry Run unexpectedly wrote to filesystem")
        validate_sources([{'name':'sample','url':'https://example.com/data',
                           'fields':'total = data.total\nlabel = data.name','header_name':''}])
        fields, rows = extract_rows({'data':{'total':42,'name':'test'}},
                                    'total = data.total\nlabel = data.name')
        if fields != ['total','label'] or rows != [{'total':42,'label':'test'}]:
            raise RuntimeError('JSON field extraction self-test failed')
        save_xlsx(root / 'explorer-selftest.xlsx',
                  [{'name':'sample','fields':fields,'rows':rows,'raw':{'data':42}}])
    return 0

def main() -> None:
    root = tk.Tk()
    ScheduledApiDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--self-test"]:
        raise SystemExit(self_test())
    if len(sys.argv) == 4 and sys.argv[1] == "--run-locked":
        try:
            raise SystemExit(run_locked_config(Path(sys.argv[2]), sys.argv[3]))
        except (WindowsTaskError, RunnerError, OSError, ValueError, json.JSONDecodeError) as exc:
            if sys.stderr is not None:
                print(f"Daily API job failed: {type(exc).__name__}", file=sys.stderr)
            raise SystemExit(1)
    main()
