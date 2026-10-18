"""Bilingual split-pane GUI for manual JSON API fetch and local data exports."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from api_data_explorer import (
    ExplorerError, extract_rows, fetch_json, fingerprint, load_template,
    save_raw_json, save_template, save_text, save_xlsx, validate_sources, validate_url,
)


def _blank() -> dict:
    return {"name": "API 1", "url": "https://example.com/data",
            "fields": "name = data.name\nvalue = data.value",
            "header_name": ""}


class ApiDataExplorerPanel(ttk.Frame):
    """A user chooses API URLs and JSON fields on the left; reads output on right.

    The configuration preview is completely offline. Live GET is separate and
    requires approval for the exact currently visible form revision.
    """

    def __init__(self, master, *, japanese: bool, initial_sources=None):
        super().__init__(master)
        self.japanese = japanese
        self.sources = [dict(x) for x in (initial_sources or [_blank()])]
        self.tokens: dict[int, str] = {}  # ephemeral per-source credential
        self.active = 0
        self.busy = False
        self.preview_revision: str | None = None
        self.result_revision: str | None = None
        self.results: list[dict] = []
        self.messages: queue.Queue = queue.Queue()
        self._render()
        self._show_source(0)

    def t(self, ja: str, en: str) -> str:
        return ja if self.japanese else en

    def sources_snapshot(self) -> list[dict]:
        self._sync_source()
        return [dict(s) for s in self.sources]

    def _render(self) -> None:
        self.columnconfigure(0, weight=2, minsize=360)
        self.columnconfigure(1, weight=3, minsize=440)
        self.rowconfigure(1, weight=1)

        header = ttk.Label(self, text=self.t(
            "APIデータ取得：左で設定 → 試運転 → 取得 → 右で確認・保存",
            "API data explorer: configure left → preview → fetch → review/save right"),
            font=("Segoe UI", 12, "bold"))
        header.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4))
        left = ttk.LabelFrame(self, text=self.t("① 接続先と欲しいJSON項目", "1. API sources and JSON fields"), padding=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=5)
        right = ttk.LabelFrame(self, text=self.t("② 取得したデータ", "2. Fetched data"), padding=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=5)
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=2)
        right.rowconfigure(4, weight=1)

        ttk.Label(left, text=self.t("APIを追加できます（最大10件）。1件ごとに欲しい項目を設定します。",
                                    "Add up to 10 APIs, each with its own fields."),
                  wraplength=350).grid(row=0, column=0, sticky="w")
        group = ttk.Frame(left)
        group.grid(row=1, column=0, sticky="ew", pady=4)
        group.columnconfigure(0, weight=1)
        self.source_list = tk.Listbox(group, height=3, exportselection=False)
        self.source_list.grid(row=0, column=0, rowspan=2, sticky="ew")
        self.source_list.bind("<<ListboxSelect>>", self._change_source)
        ttk.Button(group, text=self.t("+ 追加", "+ Add"), command=self._add_source).grid(row=0, column=1, padx=4)
        ttk.Button(group, text=self.t("削除", "Remove"), command=self._remove_source).grid(row=1, column=1, padx=4)
        self.name_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.header_var = tk.StringVar()
        self.secret_var = tk.StringVar()

        self._label_entry(left, 2, self.t("接続名", "Source name"), self.name_var)
        self._label_entry(left, 3, self.t("HTTPS API URL (GETのみ)", "HTTPS API URL (GET only)"), self.url_var)
        ttk.Label(left, text=self.t(
            "秘密鍵はURLに入れないでください。必要なら下の認証ヘッダーを利用します。",
            "Never put API keys in URLs. Use the optional authentication header."),
            wraplength=330).grid(row=4, column=0, sticky="w", pady=(2, 6))
        self._label_entry(left, 5, self.t("認証ヘッダー名（任意、例：X-API-Key）",
                                               "Auth header name (optional: X-API-Key)"), self.header_var)
        ttk.Label(left, text=self.t("認証値（保存しません）", "Auth value (not saved)")).grid(row=6, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.secret_var, show="*").grid(row=7, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(left, text=self.t(
            "欲しい項目を1行ずつ。左は表示名、右はJSONの場所です。\n"
            "例：売上 = data.sales\n商品 = items[*].name\n金額 = items[*].price",
            "One field per line: label = JSON path.\n"
            "e.g. Sales = data.sales\nProduct = items[*].name\nPrice = items[*].price"),
            wraplength=330).grid(row=8, column=0, sticky="w")
        self.fields_editor = tk.Text(left, height=7, wrap="none")
        self.fields_editor.grid(row=9, column=0, sticky="nsew", pady=3)
        left.rowconfigure(9, weight=1)
        actions = ttk.Frame(left)
        actions.grid(row=10, column=0, sticky="ew", pady=4)
        self.preview_btn = ttk.Button(actions, text=self.t("設定を試運転", "Offline preview"), command=self._preview)
        self.preview_btn.pack(side="left")
        self.fetch_btn = ttk.Button(actions, text=self.t("データを取得", "Fetch GET"), command=self._fetch)
        self.fetch_btn.pack(side="left", padx=5)
        files = ttk.Frame(left)
        files.grid(row=11, column=0, sticky="w", pady=(5, 0))
        ttk.Button(files, text=self.t("テンプレ保存", "Save template"), command=self._save_template).pack(side="left")
        ttk.Button(files, text=self.t("テンプレ読込", "Load template"), command=self._load_template).pack(side="left", padx=6)
        ttk.Label(left, text=self.t(
            "試運転は通信しません。取得は明示的なGETのみ・自動再送なし。\n"
            "この画面の取得は手動です。旧定期実行は別タブです。",
            "Preview is offline. Fetch sends explicit GET only, without retries.\n"
            "This view fetches manually; legacy scheduling stays in its own tab."),
            wraplength=360).grid(row=12, column=0, sticky="w", pady=(8, 0))

        ttk.Label(right, text=self.t(
            "取得後、APIごとに結果を表示します。数値はExcel内でも数値、文字列は文字列として保持。",
            "Results appear per API; numbers stay numeric in Excel, text stays text."),
            wraplength=530).grid(row=0, column=0, sticky="w")
        self.result_source = ttk.Combobox(right, state="readonly")
        self.result_source.grid(row=1, column=0, sticky="ew", pady=5)
        self.result_source.bind("<<ComboboxSelected>>", self._show_result)
        self.table = ttk.Treeview(right, show="headings", height=10)
        self.table.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(right, orient="horizontal", command=self.table.xview)
        self.table.configure(xscrollcommand=scroll.set)
        scroll.grid(row=3, column=0, sticky="ew")
        self.raw_view = tk.Text(right, height=7, wrap="word")
        self.raw_view.grid(row=4, column=0, sticky="nsew", pady=(6, 2))
        self.raw_view.configure(state="disabled")
        exports = ttk.Frame(right)
        exports.grid(row=5, column=0, sticky="w", pady=4)
        ttk.Button(exports, text=self.t("Excel保存", "Save Excel .xlsx"),
                   command=lambda: self._export("xlsx")).pack(side="left")
        ttk.Button(exports, text=self.t("文字列保存", "Save text .txt"),
                   command=lambda: self._export("txt")).pack(side="left", padx=4)
        ttk.Button(exports, text=self.t("元JSON保存", "Save JSON"),
                   command=lambda: self._export("json")).pack(side="left")
        self.status = tk.StringVar(value=self.t("設定してください（通信なし）", "Ready (no network)"))
        ttk.Label(self, textvariable=self.status, wraplength=850).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 10))

    @staticmethod
    def _label_entry(parent, line: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=line * 2 + 9, column=0, sticky="w")

    def _show_source(self, index: int) -> None:
        source = self.sources[index]
        self.active = index
        self.source_list.delete(0, "end")
        for i, s in enumerate(self.sources):
            self.source_list.insert("end", f"{i+1}. {s['name']}")
        self.source_list.selection_set(index)
        self.name_var.set(source["name"])
        self.url_var.set(source["url"])
        self.header_var.set(source.get("header_name", ""))
        self.secret_var.set(self.tokens.get(index, ""))
        self.fields_editor.delete("1.0", "end")
        self.fields_editor.insert("1.0", source["fields"])

    def _sync_source(self) -> None:
        if not hasattr(self, "fields_editor") or not self.sources:
            return
        self.sources[self.active] = {
            "name": self.name_var.get().strip(),
            "url": self.url_var.get().strip(),
            "fields": self.fields_editor.get("1.0", "end").strip(),
            "header_name": self.header_var.get().strip(),
        }
        self.tokens[self.active] = self.secret_var.get()

    def _change_source(self, _event=None) -> None:
        if self.busy:
            self.source_list.selection_clear(0, "end")
            self.source_list.selection_set(self.active)
            return
        chosen = self.source_list.curselection()
        if chosen and chosen[0] != self.active:
            self._sync_source()
            self._show_source(chosen[0])

    def _add_source(self) -> None:
        if self.busy or len(self.sources) >= 10:
            return
        self._sync_source()
        index = len(self.sources)
        blank = _blank()
        blank["name"] = f"API {index+1}"
        self.sources.append(blank)
        self._show_source(index)

    def _remove_source(self) -> None:
        if self.busy or len(self.sources) < 2:
            return
        self._sync_source()
        self.sources.pop(self.active)
        self.tokens.clear()  # avoid accidentally sending old token to a different host
        self._show_source(min(self.active, len(self.sources)-1))

    def _current_revision(self) -> str:
        self._sync_source()
        return fingerprint(self.sources)

    def _preview(self) -> None:
        if self.busy:
            return
        try:
            revision = self._current_revision()
        except (ExplorerError, ValueError) as exc:
            messagebox.showerror(self.t("設定エラー", "Invalid configuration"), str(exc), parent=self)
            return
        self.preview_revision = revision
        self.result_revision = None
        self.results = []
        self.result_source.configure(values=[])
        self._clear_result()
        self.status.set(self.t(
            f"設定確認OK：{len(self.sources)}件。通信なし。内容を確認して「データを取得」へ。",
            f"Preview OK: {len(self.sources)} API(s). No network call. Confirm and fetch."))

    def _fetch(self) -> None:
        if self.busy:
            return
        try:
            revision = self._current_revision()
        except (ExplorerError, ValueError) as exc:
            messagebox.showerror(self.t("設定エラー", "Invalid configuration"), str(exc), parent=self)
            return
        if revision != self.preview_revision:
            messagebox.showwarning(self.t("試運転が必要", "Preview required"), self.t(
                "入力を変更した場合は再度試運転してください。",
                "Run offline preview again after changing settings."), parent=self)
            return
        hosts = sorted({validate_url(s["url"])[0] for s in self.sources})
        prompt = self.t(
            f"実際に{len(self.sources)}件のAPIへGET通信します。接続先：{', '.join(hosts)}。\n"
            "返信データは画面に表示され、保存は別途選択します。続行しますか？",
            f"Send GET requests to {len(self.sources)} API(s): {', '.join(hosts)}?\n"
            "Data will be shown locally; saving requires another action.")
        if not messagebox.askyesno(self.t("実APIアクセス", "Live API access"), prompt, parent=self):
            return
        self.preview_revision = None  # consume authorization before any network effect
        self.results = []
        self.result_revision = None
        self._clear_result()
        self.busy = True
        self.preview_btn.configure(state="disabled")
        self.fetch_btn.configure(state="disabled")
        self.status.set(self.t("取得中…", "Fetching…"))
        sources = [dict(s) for s in self.sources]
        tokens = dict(self.tokens)

        def work() -> None:
            successes = []
            failures = []
            for index, source in enumerate(sources):
                try:
                    raw = fetch_json(source["url"], source["header_name"], tokens.get(index, ""))
                    fields, rows = extract_rows(raw, source["fields"])
                    successes.append({"name": source["name"], "fields": fields, "rows": rows, "raw": raw})
                except Exception as exc:
                    failures.append(f"{source['name']}: {type(exc).__name__}")
            self.messages.put((revision, successes, failures))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self._poll)

    def _poll(self) -> None:
        try:
            revision, results, errors = self.messages.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(100, self._poll)
            return
        self.busy = False
        self.preview_btn.configure(state="normal")
        self.fetch_btn.configure(state="normal")
        try:
            unchanged = self._current_revision() == revision
        except (ExplorerError, ValueError):
            unchanged = False
        if not unchanged:
            self.status.set(self.t("取得中に設定変更：結果を破棄しました", "Settings changed; results discarded"))
            return
        self.results = results
        self.result_revision = revision if results else None
        self.result_source.configure(values=[item["name"] for item in results])
        if results:
            self.result_source.current(0)
            self._show_result()
        self.status.set(self.t(
            f"取得成功：{len(results)}件 / 失敗：{len(errors)}件（再送なし）",
            f"Fetched: {len(results)} / failed: {len(errors)} (no retry)"))
        if errors:
            messagebox.showwarning(self.t("一部のAPIが失敗", "Some sources failed"),
                                   "\n".join(errors), parent=self)

    def _clear_result(self) -> None:
        self.table.configure(columns=())
        for item in self.table.get_children():
            self.table.delete(item)
        self.raw_view.configure(state="normal")
        self.raw_view.delete("1.0", "end")
        self.raw_view.configure(state="disabled")

    def _show_result(self, _event=None) -> None:
        if not self.results:
            return
        index = self.result_source.current()
        if not 0 <= index < len(self.results):
            return
        result = self.results[index]
        self._clear_result()
        cols = [f"c{i}" for i, _ in enumerate(result["fields"])]
        self.table.configure(columns=cols)
        for col, label in zip(cols, result["fields"]):
            self.table.heading(col, text=label)
            self.table.column(col, width=150, minwidth=80, stretch=True)
        for row in result["rows"][:500]:
            self.table.insert("", "end", values=[
                str(row.get(label, ""))[:400] for label in result["fields"]])
        self.raw_view.configure(state="normal")
        self.raw_view.insert("1.0", json.dumps(result["raw"], ensure_ascii=False, indent=2)[:30_000])
        self.raw_view.configure(state="disabled")

    def _export(self, mode: str) -> None:
        if self.busy or not self.results:
            messagebox.showwarning(self.t("結果がありません", "No results"),
                                   self.t("先にデータを取得してください", "Fetch data first"), parent=self)
            return
        try:
            if self._current_revision() != self.result_revision:
                raise ExplorerError("Settings changed; fetch again before exporting")
            extension = {"xlsx": ".xlsx", "txt": ".txt", "json": ".json"}[mode]
            path = filedialog.asksaveasfilename(parent=self, defaultextension=extension,
                                               initialfile="api-data" + extension)
            if not path:
                return
            writer = {"xlsx": save_xlsx, "txt": save_text, "json": save_raw_json}[mode]
            writer(path, self.results)
        except (OSError, ExplorerError, ValueError) as exc:
            messagebox.showerror(self.t("保存エラー", "Save failed"), str(exc), parent=self)
            return
        self.status.set(self.t("新規ファイルに保存しました", "Saved to a new file"))

    def _save_template(self) -> None:
        if self.busy:
            return
        try:
            self._current_revision()
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                                initialfile="api-fields-template.json")
            if path:
                save_template(path, self.sources)
                self.status.set(self.t("秘密値を除いてテンプレ保存", "Template saved without secrets"))
        except (ExplorerError, OSError, ValueError) as exc:
            messagebox.showerror(self.t("保存エラー", "Save failed"), str(exc), parent=self)

    def _load_template(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            sources = load_template(path)
        except (ExplorerError, OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror(self.t("読み込みエラー", "Load failed"), str(exc), parent=self)
            return
        self.sources = sources
        self.tokens.clear()
        self.preview_revision = None
        self.result_revision = None
        self.results = []
        self.result_source.configure(values=[])
        self._clear_result()
        self._show_source(0)
        self.status.set(self.t("設定を読み込みました。試運転してください。",
                               "Template loaded; run offline preview."))
