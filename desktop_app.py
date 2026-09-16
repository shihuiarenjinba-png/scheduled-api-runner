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

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ScheduledApiDesktop:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Scheduled API Runner / 定期API実行")
        self.root.geometry("1080x740")
        self.root.minsize(900, 620)
        self.config_path = tk.StringVar()
        self.status = tk.StringVar(value="Ready / 準備完了")
        self.config: dict | None = None
        self.monitor_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self._build()
        default = Path(__file__).resolve().parent / "jobs.example.json"
        if default.is_file():
            self.config_path.set(str(default))
            self._load_config(False)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Scheduled API Runner", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="許可したHTTPSホストへ、決められたジョブだけを実行します。秘密値は画面に表示しません。").pack(anchor="w", pady=(0, 14))

        cfg = ttk.LabelFrame(outer, text="Configuration / 設定", padding=10)
        cfg.pack(fill="x", pady=(0, 10))
        ttk.Entry(cfg, textvariable=self.config_path).pack(side="left", fill="x", expand=True)
        ttk.Button(cfg, text="Browse / 選択", command=self._browse).pack(side="left", padx=(8, 0))
        ttk.Button(cfg, text="Validate / 検証", command=lambda: self._load_config(True)).pack(side="left", padx=(6, 0))

        info = ttk.LabelFrame(outer, text="Jobs / ジョブ概要", padding=8)
        info.pack(fill="both", expand=True, pady=(0, 10))
        cols = ("name", "schedule", "method", "host", "enabled")
        self.jobs = ttk.Treeview(info, columns=cols, show="headings", height=8)
        labels = ("Name / 名前", "Schedule / 時刻", "Method", "Host (secret-free)", "Enabled")
        widths = (200, 210, 90, 330, 80)
        for col, label, width in zip(cols, labels, widths):
            self.jobs.heading(col, text=label)
            self.jobs.column(col, width=width, anchor="w")
        self.jobs.pack(fill="both", expand=True)
        self.host_label = ttk.Label(info, text="Allow hosts: -")
        self.host_label.pack(anchor="w", pady=(8, 0))

        actions = ttk.LabelFrame(outer, text="Execution / 実行", padding=10)
        actions.pack(fill="x", pady=(0, 10))
        self.dry_btn = ttk.Button(actions, text="Dry Run All / 全ジョブ確認", command=self._dry_run)
        self.dry_btn.pack(side="left")
        self.run_btn = ttk.Button(actions, text="Run Enabled Once / 有効ジョブ1回実行", command=self._live_once)
        self.run_btn.pack(side="left", padx=6)
        self.start_btn = ttk.Button(actions, text="Start Scheduler / 定期実行開始", command=self._start_scheduler)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text="Stop / 停止", command=self._stop_scheduler, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Label(actions, text="Live実行は外部APIへ実際に送信します。Dry Runを先に実行してください。", wraplength=410).pack(side="right")

        logbox = ttk.LabelFrame(outer, text="Audit view / 実行表示", padding=8)
        logbox.pack(fill="both", expand=True)
        self.log = tk.Text(logbox, wrap="word", height=13, state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(logbox, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(outer, textvariable=self.status).pack(fill="x", pady=(8, 0))

    def _browse(self) -> None:
        path = filedialog.askopenfilename(title="Scheduled API JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            self.config_path.set(path)
            self._load_config(True)

    def _read_raw(self) -> dict:
        path = Path(self.config_path.get()).expanduser().resolve()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RunnerError("config root must be an object")
        return raw

    @staticmethod
    def _job_summary(job: dict) -> tuple[str, str, str, str, str]:
        name = str(job.get("name", "unnamed"))
        schedule = job.get("schedule", {}) if isinstance(job.get("schedule", {}), dict) else {}
        schedule_type = str(schedule.get("type", "?"))
        if schedule_type == "daily":
            schedule_text = f"daily {schedule.get('at', '?')}"
        elif schedule_type == "interval":
            schedule_text = f"every {schedule.get('seconds', '?')} sec"
        else:
            schedule_text = schedule_type
        request = job.get("request", {}) if isinstance(job.get("request", {}), dict) else {}
        method = str(request.get("method", "GET")).upper()
        raw_url = str(request.get("url", ""))
        try:
            parsed = urllib.parse.urlparse(raw_url)
            host = parsed.hostname or "(ENV/unknown)"
        except Exception:
            host = "(invalid)"
        return name, schedule_text, method, host, "yes" if job.get("enabled", True) else "no"

    def _load_config(self, show_error: bool) -> bool:
        try:
            raw = self._read_raw()
            # Full validation also resolves environment-variable references, but never sends a request in dry-run mode.
            ScheduledRunner(raw, dry_run=True)
            self.config = raw
            self._render_summary(raw)
            self.status.set("Configuration valid / 設定OK")
            return True
        except Exception as exc:
            self.config = None
            self.status.set(f"Configuration error / 設定エラー: {type(exc).__name__}")
            if show_error:
                messagebox.showerror("Configuration", str(exc))
            return False

    def _render_summary(self, raw: dict) -> None:
        for item in self.jobs.get_children():
            self.jobs.delete(item)
        for job in raw.get("jobs", []):
            if isinstance(job, dict):
                self.jobs.insert("", "end", values=self._job_summary(job))
        hosts = [str(x) for x in raw.get("allow_hosts", [])]
        self.host_label.configure(text="Allow hosts / 許可ホスト: " + (", ".join(hosts) if hosts else "-"))

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
        self.status.set("Dry Run… / 確認中…")
        def worker() -> None:
            try:
                text = self._capture(lambda: ScheduledRunner(raw, dry_run=True).run_all_once())
                self.root.after(0, lambda: self._finish(True, text or "Dry Run OK", "Dry Run complete / 確認完了"))
            except Exception as exc:
                self.root.after(0, lambda: self._finish(False, f"{type(exc).__name__}: {exc}", "Dry Run failed / 確認失敗"))
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
        risk = "\nPOST/PUT/PATCH/DELETEを含む有効ジョブがあります。" if self._has_mutating_jobs() else ""
        mode = "定期実行を開始" if scheduled else "有効ジョブを今すぐ1回実行"
        return messagebox.askyesno("Live API execution / 実API実行", f"{mode}します。外部APIへ実際に送信されます。{risk}\n\nDry Runと設定確認が済んでいる場合だけ続行してください。")

    def _live_once(self) -> None:
        if not self._load_config(True) or not self._confirm_live(False):
            return
        assert self.config is not None
        raw = self.config
        self.status.set("Running live requests… / 実API実行中…")
        def worker() -> None:
            try:
                text = self._capture(lambda: ScheduledRunner(raw, dry_run=False).run_all_once())
                self.root.after(0, lambda: self._finish(True, text or "Run OK", "Run complete / 実行完了"))
            except Exception as exc:
                self.root.after(0, lambda: self._finish(False, f"{type(exc).__name__}: {exc}", "Run failed / 実行失敗"))
        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, ok: bool, text: str, status: str) -> None:
        self._append(text)
        self.status.set(status)
        if not ok:
            messagebox.showerror("Scheduled API Runner", text[-1500:])

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
        self.status.set("Scheduler running / 定期実行中")
        def loop() -> None:
            try:
                runner = ScheduledRunner(raw, dry_run=False)
                while not self.stop_event.is_set():
                    text = self._capture(runner.run_due)
                    if text:
                        self.root.after(0, lambda t=text: self._append(t))
                    self.stop_event.wait(runner.poll_seconds)
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Scheduler", f"{type(exc).__name__}: {exc}"))
            finally:
                self.root.after(0, self._scheduler_stopped)
        self.monitor_thread = threading.Thread(target=loop, daemon=True)
        self.monitor_thread.start()

    def _stop_scheduler(self) -> None:
        self.stop_event.set()
        self.status.set("Stopping… / 停止中…")

    def _scheduler_stopped(self) -> None:
        self.monitor_thread = None
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.dry_btn.configure(state="normal")
        self.status.set("Stopped / 停止しました")


def main() -> None:
    root = tk.Tk()
    ScheduledApiDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
