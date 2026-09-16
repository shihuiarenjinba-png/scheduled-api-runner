from __future__ import annotations

import contextlib
import io
import json
import threading
import urllib.parse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from scheduled_api_runner import RunnerError, ScheduledRunner
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
        self.status = tk.StringVar(value="")
        self.config: dict | None = None
        self.monitor_thread: threading.Thread | None = None
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
        for child in self.root.winfo_children():
            child.destroy()
        self.root.title(self.t("定期API実行", "Scheduled API Runner"))

        outer = ttk.Frame(self.root, padding=18)
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
                "許可したHTTPSホストへ、決められたジョブだけを実行します。秘密値は画面に表示しません。",
                "Runs only configured jobs against allowed HTTPS hosts. Secret values are not shown in the UI.",
            ),
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

        logbox = ttk.LabelFrame(outer, text=self.t("実行表示", "Audit view"), padding=8)
        logbox.pack(fill="both", expand=True)
        self.log = tk.Text(logbox, wrap="word", height=13, state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(logbox, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(outer, textvariable=self.status).pack(fill="x", pady=(8, 0))

        if self.monitor_thread is not None:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.run_btn.configure(state="disabled")
            self.dry_btn.configure(state="disabled")

    def _language_changed(self, _event=None) -> None:
        self.lang = "en" if self.language_var.get() == "English" else "ja"
        save_language(APP_ID, self.lang)
        self._build()
        if self.config is not None:
            self._render_summary(self.config)
        self.status.set(self.t("定期実行中", "Scheduler running") if self.monitor_thread is not None else self.t("準備完了", "Ready"))

    def _browse(self) -> None:
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

    def _dry_run(self) -> None:
        if not self._load_config(True):
            return
        assert self.config is not None
        raw = self.config
        self.status.set(self.t("確認中…", "Dry Run…"))

        def worker() -> None:
            try:
                text = self._capture(lambda: ScheduledRunner(raw, dry_run=True).run_all_once())
                self.root.after(0, lambda: self._finish(True, text or "Dry Run OK", self.t("確認完了", "Dry Run complete")))
            except Exception as exc:
                self.root.after(0, lambda: self._finish(False, f"{type(exc).__name__}: {exc}", self.t("確認失敗", "Dry Run failed")))

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
            f"{mode}します。外部APIへ実際に送信されます。{risk}\n\nDry Runと設定確認が済んでいる場合だけ続行してください。",
            f"{mode}. Real requests will be sent to external APIs.{risk}\n\nContinue only after Dry Run and configuration review.",
        )
        return messagebox.askyesno(self.t("実API実行", "Live API execution"), message, parent=self.root)

    def _live_once(self) -> None:
        if not self._load_config(True) or not self._confirm_live(False):
            return
        assert self.config is not None
        raw = self.config
        self.status.set(self.t("実API実行中…", "Running live requests…"))

        def worker() -> None:
            try:
                text = self._capture(lambda: ScheduledRunner(raw, dry_run=False).run_all_once())
                self.root.after(0, lambda: self._finish(True, text or "Run OK", self.t("実行完了", "Run complete")))
            except Exception as exc:
                self.root.after(0, lambda: self._finish(False, f"{type(exc).__name__}: {exc}", self.t("実行失敗", "Run failed")))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, ok: bool, text: str, status: str) -> None:
        self._append(text)
        self.status.set(status)
        if not ok:
            messagebox.showerror(self.t("定期API実行", "Scheduled API Runner"), text[-1500:], parent=self.root)

    def _start_scheduler(self) -> None:
        if not self._load_config(True) or self.monitor_thread is not None or not self._confirm_live(True):
            return
        assert self.config is not None
        raw = self.config
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
                self.root.after(0, lambda: messagebox.showerror(self.t("スケジューラエラー", "Scheduler error"), f"{type(exc).__name__}: {exc}", parent=self.root))
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


def main() -> None:
    root = tk.Tk()
    ScheduledApiDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
