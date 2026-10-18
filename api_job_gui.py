"""Small offline Windows GUI for explicit daily JSON GET -> existing CSV jobs.

Schedule monitoring only runs while this window stays open; there is no hidden
background service and no Windows Task Scheduler changes.
"""
from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from api_job_config import ConfigurationError, build_daily_job
from scheduled_api_runner import RunnerError, ScheduledRunner
from win_task import TaskError, register, unregister


class JobWindow(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=16)
        self.pack(fill='both', expand=True)
        self.url = tk.StringVar()
        self.file = tk.StringVar()
        self.job = tk.StringVar(value='daily_api')
        self.at = tk.StringVar(value='09:00')
        self.env = tk.StringVar()
        self.policy = tk.StringVar(value='error')
        self.status = tk.StringVar(value='Set endpoint and existing CSV, then validate.')
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.saved_path: Path | None = None
        self._layout()
        master.protocol('WM_DELETE_WINDOW', self._close)

    def _layout(self):
        self.columnconfigure(1, weight=1)
        entries = [
            ('HTTPS JSON endpoint', self.url),
            ('Existing CSV to update', self.file),
            ('Job name', self.job),
            ('Daily time (local HH:MM)', self.at),
            ('Bearer token environment variable (optional)', self.env),
        ]
        for i, (label, variable) in enumerate(entries):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky='w', pady=4, padx=(0, 12))
            ttk.Entry(self, textvariable=variable).grid(row=i, column=1, sticky='ew', pady=4)
        ttk.Button(self, text='Browse CSV', command=self._browse).grid(row=1, column=2, padx=6)
        ttk.Label(self, text='CSV column = JSON field (one per line)').grid(row=5, column=0, sticky='nw', pady=8)
        self.mapping = tk.Text(self, height=6, width=48, undo=True)
        self.mapping.grid(row=5, column=1, columnspan=2, sticky='nsew')
        self.mapping.insert('1.0', 'amount=data.amount\nsymbol=data.symbol')
        self.rowconfigure(5, weight=1)
        ttk.Label(self, text='Existing date').grid(row=6, column=0, sticky='w', pady=8)
        ttk.Combobox(self, textvariable=self.policy, values=['error', 'skip', 'replace'], state='readonly').grid(row=6, column=1, sticky='w')
        controls = ttk.Frame(self)
        controls.grid(row=7, column=0, columnspan=3, sticky='ew', pady=12)
        for i, (label, callback) in enumerate([
            ('Validate', self.validate),
            ('Save configuration', self.save),
            ('Run once', self.run_once),
            ('Start daily schedule', self.start),
            ('Stop schedule', self.stop_schedule),
        ]):
            ttk.Button(controls, text=label, command=callback).grid(row=0, column=i, padx=4, sticky='w')
        task_controls = ttk.Frame(self)
        task_controls.grid(row=8, column=0, columnspan=3, sticky='w')
        ttk.Button(task_controls, text='Install Windows daily task',
                   command=self.install_windows).pack(side='left', padx=4)
        ttk.Button(task_controls, text='Remove Windows daily task',
                   command=self.remove_windows).pack(side='left', padx=4)
        ttk.Label(self, textvariable=self.status, wraplength=680).grid(row=9, column=0, columnspan=3, sticky='w')
        ttk.Label(self, foreground='#555555',
                  text='Local only. Schedule runs while this window is open; no cloud account or silent OS task registration.\n'
                       'A CSV backup is written for each successful update. Review the file before sharing.',
                  wraplength=690).grid(row=10, column=0, columnspan=3, sticky='w', pady=8)

    def _browse(self):
        chosen = filedialog.askopenfilename(title='Select existing CSV', filetypes=[('CSV', '*.csv')])
        if chosen:
            self.file.set(chosen)

    def _config(self):
        return build_daily_job(url=self.url.get(), csv_path=self.file.get(),
                               mapping=self.mapping.get('1.0', 'end-1c'),
                               job_name=self.job.get(), at=self.at.get(),
                               duplicate_policy=self.policy.get(), token_env_name=self.env.get())

    def validate(self):
        try:
            cfg = self._config()
            self.status.set('Configuration valid: ' + cfg['jobs'][0]['persist']['target_file'] + '; no network request made.')
        except (ConfigurationError, OSError, ValueError) as exc:
            messagebox.showerror('Review settings', str(exc))

    def save(self):
        try:
            cfg = self._config()
            chosen = filedialog.asksaveasfilename(title='Save new job settings', defaultextension='.json',
                                                  initialfile=self.job.get() + '.json',
                                                  filetypes=[('JSON', '*.json')])
            if not chosen:
                return
            with Path(chosen).open('x', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.saved_path = Path(chosen).resolve()
            self.status.set('Settings saved. Windows task registration is now available.')
        except FileExistsError:
            messagebox.showerror('Not overwritten', 'This settings file exists. Choose a new filename.')
        except (ConfigurationError, OSError, ValueError) as exc:
            messagebox.showerror('Cannot save', str(exc))

    def _report(self, success: bool, action: str, detail: str):
        self.status.set(action + ': ' + ('complete' if success else 'failed') + ' — ' + detail)
        if not success:
            messagebox.showerror('Job did not complete', detail)

    def run_once(self):
        try:
            cfg = self._config()
        except (ConfigurationError, OSError, ValueError) as exc:
            messagebox.showerror('Review settings', str(exc))
            return
        self.status.set('Running one HTTPS GET (the CSV may be updated)...')
        def job():
            try:
                ScheduledRunner(cfg).run_all_once()
                self.after(0, self._report, True, 'One-time run', 'Inspect output and backup')
            except Exception as exc:
                self.after(0, self._report, False, 'One-time run', type(exc).__name__ + ': ' + str(exc))
        threading.Thread(target=job, daemon=True).start()

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            self.status.set('Schedule is already active.')
            return
        try:
            cfg = self._config()
        except (ConfigurationError, OSError, ValueError) as exc:
            messagebox.showerror('Review settings', str(exc))
            return
        self.stop.clear()
        def loop():
            try:
                runner = ScheduledRunner(cfg)
                while not self.stop.is_set():
                    try:
                        runner.run_due()
                    except Exception as exc:
                        self.after(0, self._report, False, 'Scheduled run', type(exc).__name__)
                    self.stop.wait(10)
            finally:
                self.after(0, self.status.set, 'Schedule stopped; no background service was installed.')
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()
        self.status.set('Daily schedule active only while this window remains open.')

    def stop_schedule(self):
        self.stop.set()
        self.status.set('Stopping schedule; an ongoing request may finish first.')

    def _close(self):
        self.stop.set()
        self.winfo_toplevel().destroy()


def main():
    root = tk.Tk()
    root.title('Scheduled API Runner — Dated CSV update')
    root.minsize(750, 450)
    JobWindow(root)
    root.mainloop()


if __name__ == '__main__':
    main()
