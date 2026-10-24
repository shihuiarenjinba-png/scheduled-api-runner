"""Read-only JSON API inspector: safe HTTPS fetch, JSON path extraction and exports.

No external LLM, server, paid API, background upload, or implicit execution.
The Tk UI is responsible for explicit user confirmation before network calls.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
from urllib.parse import parse_qsl, urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


MAX_BYTES = 2_000_000
MAX_SOURCES = 10
MAX_ROWS = 50_000
MAX_FIELDS = 32
_BLOCKED_QUERY = {"api_key", "apikey", "key", "token", "access_token",
                  "secret", "signature", "password", "client_secret"}
_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")


class ExplorerError(ValueError):
    pass


def validate_url(url: str) -> tuple[str, str]:
    """Return (public DNS host, HTTPS request target), never do DNS in preview."""
    if not isinstance(url, str) or any(ord(c) < 33 for c in url):
        raise ExplorerError("Enter one complete HTTPS URL without spaces/control characters")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ExplorerError("Invalid HTTPS address") from exc
    if (parts.scheme != "https" or not host or parts.username or parts.password
            or parts.fragment or port not in (None, 443)):
        raise ExplorerError("Only HTTPS DNS hosts on port 443; no URL credentials or fragments")
    name = host.lower().rstrip(".")
    if (name in {"localhost"} or name.endswith((".local", ".internal", ".localhost"))
            or "." not in name or not re.fullmatch(r"[a-z0-9.-]+", name)):
        raise ExplorerError("Choose a public DNS hostname")
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise ExplorerError("IP literal targets are not supported")
    if any(k.lower() in _BLOCKED_QUERY for k, _ in parse_qsl(parts.query, keep_blank_values=True)):
        raise ExplorerError("Do not place API keys/tokens in the URL query")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return name, path


def tokenize(path: str) -> tuple[object, ...]:
    """Small JSON-path subset: $.items[*].price, orders[0].name, 総計.売上."""
    value = str(path).strip()
    if value.startswith("$"):
        value = value[1:]
        if value.startswith("."):
            value = value[1:]
    if not value:
        raise ExplorerError("Enter a JSON field path")
    tokens: list[object] = []
    index = 0
    while index < len(value):
        if value[index] == ".":
            if index == 0 or value[index - 1] == "." or index == len(value) - 1:
                raise ExplorerError("Invalid JSON path separator")
            index += 1
            continue
        if value[index] == "[":
            end = value.find("]", index + 1)
            if end == -1:
                raise ExplorerError("Unclosed JSON array index")
            raw = value[index + 1:end]
            if raw == "*":
                tokens.append("*")
            elif raw.isascii() and raw.isdigit():
                tokens.append(int(raw))
            else:
                raise ExplorerError("Use [0] or [*] for JSON arrays")
            index = end + 1
        else:
            matched = re.match(r"[^\s.\[\]]+", value[index:])
            if not matched:
                raise ExplorerError("Invalid JSON field name")
            tokens.append(matched.group())
            index += len(matched.group())
        if index < len(value) and value[index] not in ".[":
            raise ExplorerError("Missing dot between JSON field names")
    if tokens.count("*") > 1:
        raise ExplorerError("Use only one [*] level per field")
    return tuple(tokens)


def parse_fields(source: str) -> list[tuple[str, tuple[object, ...]]]:
    fields: list[tuple[str, tuple[object, ...]]] = []
    seen: set[str] = set()
    for line in source.splitlines():
        if not line.strip():
            continue
        label, sep, path = line.partition("=")
        if not sep:
            label = line.strip()
            path = label
        else:
            label, path = label.strip(), path.strip()
        if not label or len(label) > 70 or label in seen:
            raise ExplorerError("Field labels must be unique and 1-70 characters")
        seen.add(label)
        fields.append((label, tokenize(path)))
    if not 1 <= len(fields) <= MAX_FIELDS:
        raise ExplorerError("Specify 1 to 32 data fields, one per line")
    prefixes = {tokens[:tokens.index("*")] for _, tokens in fields if "*" in tokens}
    if len(prefixes) > 1:
        raise ExplorerError("All [*] paths must refer to the same array")
    return fields


def validate_sources(sources: list[dict]) -> list[dict]:
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ExplorerError("Add between 1 and 10 API sources")
    validated: list[dict] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ExplorerError("Invalid API source")
        name = str(source.get("name", "")).strip()
        if not name or len(name) > 60 or any(c in name for c in "\r\n"):
            raise ExplorerError("Each API source needs a short name")
        url = str(source.get("url", "")).strip()
        validate_url(url)
        fields_text = str(source.get("fields", ""))
        parse_fields(fields_text)
        header = str(source.get("header_name", "")).strip()
        if header and (not _HEADER_RE.fullmatch(header) or
                       header.lower() in {"host", "content-length", "connection",
                                          "proxy-authorization", "cookie"}):
            raise ExplorerError("Unsupported authentication header name")
        validated.append({"name": name, "url": url, "fields": fields_text, "header_name": header})
    return validated


def fingerprint(sources: list[dict]) -> str:
    valid = validate_sources(sources)
    return hashlib.sha256(json.dumps(valid, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


_MISSING = object()


def _resolve(value: object, tokens: tuple[object, ...]) -> object:
    for key in tokens:
        if isinstance(key, str) and isinstance(value, dict):
            value = value.get(key, _MISSING)
        elif isinstance(key, int) and isinstance(value, list) and 0 <= key < len(value):
            value = value[key]
        else:
            return _MISSING
    return value


def _cell(value: object) -> object:
    if value is _MISSING or value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if not isinstance(value, float) or math.isfinite(value) else str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def extract_rows(document: object, field_text: str) -> tuple[list[str], list[dict]]:
    fields = parse_fields(field_text)
    prefix = next((p[:p.index("*")] for _, p in fields if "*" in p), None)
    if prefix is None:
        contexts = [(document, None)]
    else:
        items = _resolve(document, prefix)
        if items is _MISSING or items is None:
            items = []
        if not isinstance(items, list):
            raise ExplorerError("The [*] path did not locate a JSON array")
        if len(items) > MAX_ROWS:
            raise ExplorerError("API response contains too many rows")
        contexts = [(document, item) for item in items]
    rows = []
    for root, item in contexts:
        row = {}
        for label, path in fields:
            if "*" in path:
                value = _resolve(item, path[path.index("*") + 1:])
            else:
                value = _resolve(root, path)
            row[label] = _cell(value)
        rows.append(row)
    return [label for label, _ in fields], rows


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Connect only to a validated public IP, but verify TLS for original DNS host."""
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise


def fetch_json(url: str, header_name: str = "", header_value: str = "") -> object:
    """One explicit GET; no redirects, retries, proxies, cookies or writes."""
    host, path = validate_url(url)
    if bool(header_name) != bool(header_value):
        raise ExplorerError("Provide both authentication header name and value")
    if header_name:
        validate_sources([{"name": "request", "url": url, "fields": "status", "header_name": header_name}])
    if any(c in header_value for c in "\r\n"):
        raise ExplorerError("Header value contains prohibited control characters")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = [entry[4][0] for entry in addresses]
        if not ips or not all(ipaddress.ip_address(x).is_global for x in ips):
            raise ExplorerError("Destination DNS resolves to a non-public address")
        conn = _PinnedHTTPS(host, ips[0], timeout=15.0)
        try:
            headers = {"Accept": "application/json", "User-Agent": "ScheduledApiRunner-Explorer/1"}
            if header_name:
                headers[header_name] = header_value
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            if not 200 <= response.status < 300:
                raise ExplorerError(f"API returned HTTP {response.status} (no automatic retry)")
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ExplorerError("JSON exceeds the 2 MB safety limit")
        finally:
            conn.close()
        decoded = json.loads(data.decode("utf-8-sig"))
        if not isinstance(decoded, (dict, list)):
            raise ExplorerError("JSON response must be an object or array")
        return decoded
    except (OSError, ssl.SSLError, UnicodeError, json.JSONDecodeError, http.client.HTTPException) as exc:
        # Never echo endpoint paths, query values, tokens or server response bodies.
        raise ExplorerError(f"Could not read JSON response ({type(exc).__name__})") from None


def _publish_new(path: str | Path, writer) -> Path:
    target = Path(path).expanduser()
    if not target.parent.is_dir():
        raise ExplorerError("Choose an existing output folder")
    if target.exists():
        raise FileExistsError("Output already exists; choose a new file name")
    fd, tmpname = tempfile.mkstemp(prefix=".api-export-", dir=target.parent)
    os.close(fd)
    temp = Path(tmpname)
    try:
        writer(temp)
        # Same-directory exclusive hard link: a competing writer cannot be overwritten.
        os.link(temp, target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def save_template(path: str | Path, sources: list[dict]) -> Path:
    safe = validate_sources(sources)
    return _publish_new(path, lambda tmp: tmp.write_text(
        json.dumps({"schema_version": 1, "sources": safe}, ensure_ascii=False, indent=2),
        encoding="utf-8"))


def load_template(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ExplorerError("Unsupported API template")
    return validate_sources(data.get("sources", []))


def save_raw_json(path: str | Path, results: list[dict]) -> Path:
    raw = [{"source": item["name"], "response": item["raw"]} for item in results]
    return _publish_new(path, lambda tmp: tmp.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"))


def save_text(path: str | Path, results: list[dict]) -> Path:
    lines = []
    for result in results:
        lines.append("[" + result["name"] + "]")
        for idx, row in enumerate(result["rows"], 1):
            for label, value in row.items():
                if isinstance(value, str):
                    lines.append(f"{idx}. {label}: {value}")
        lines.append("")
    return _publish_new(path, lambda tmp: tmp.write_text("\n".join(lines), encoding="utf-8"))


def _col_letter(num: int) -> str:
    result = ""
    while num:
        num, remain = divmod(num - 1, 26)
        result = chr(65 + remain) + result
    return result


def save_xlsx(path: str | Path, results: list[dict]) -> Path:
    """Small, dependency-free XLSX writer. Numeric JSON values remain numeric."""
    if not results:
        raise ExplorerError("There are no fetched results to export")
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ET.register_namespace("", ns)

    def cell(parent, address: str, value: object) -> None:
        is_numeric = (isinstance(value, (int, float)) and not isinstance(value, bool)
                      and (not isinstance(value, float) or math.isfinite(value)))
        c = ET.SubElement(parent, f"{{{ns}}}c", {"r": address, "t": "n" if is_numeric else "inlineStr"})
        if is_numeric:
            ET.SubElement(c, f"{{{ns}}}v").text = str(value)
        else:
            inline = ET.SubElement(c, f"{{{ns}}}is")
            text = ET.SubElement(inline, f"{{{ns}}}t")
            text.text = str(value)
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    def write(temp: Path) -> None:
        with ZipFile(temp, "w", compression=ZIP_DEFLATED) as archive:
            workbook = ET.Element(f"{{{ns}}}workbook")
            sheets = ET.SubElement(workbook, f"{{{ns}}}sheets")
            rels = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
            for i, result in enumerate(results, 1):
                name = re.sub(r"[\[\]*:/\\?]", "_", result["name"])[:31] or "API"
                ET.SubElement(sheets, f"{{{ns}}}sheet", {
                    "name": f"{name[:26]}_{i}", "sheetId": str(i),
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": f"rId{i}"})
                ET.SubElement(rels, "Relationship", {
                    "Id": f"rId{i}", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                    "Target": f"worksheets/sheet{i}.xml"})
                sheet = ET.Element(f"{{{ns}}}worksheet")
                data = ET.SubElement(sheet, f"{{{ns}}}sheetData")
                headers = result["fields"]
                if len(result["rows"]) > MAX_ROWS or len(headers) > MAX_FIELDS:
                    raise ExplorerError("Export row/column limit exceeded")
                header_row = ET.SubElement(data, f"{{{ns}}}row", {"r": "1"})
                for col, header in enumerate(headers, 1):
                    cell(header_row, f"{_col_letter(col)}1", header)
                for row_no, row in enumerate(result["rows"], 2):
                    xml_row = ET.SubElement(data, f"{{{ns}}}row", {"r": str(row_no)})
                    for col, header in enumerate(headers, 1):
                        cell(xml_row, f"{_col_letter(col)}{row_no}", row.get(header, ""))
                archive.writestr(f"xl/worksheets/sheet{i}.xml", ET.tostring(sheet, encoding="utf-8", xml_declaration=True))
            archive.writestr("xl/workbook.xml", ET.tostring(workbook, encoding="utf-8", xml_declaration=True))
            archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(rels, encoding="utf-8", xml_declaration=True))
            archive.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""")
            types = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
            ET.SubElement(types, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
            ET.SubElement(types, "Default", {"Extension": "xml", "ContentType": "application/xml"})
            ET.SubElement(types, "Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
            for i in range(1, len(results) + 1):
                ET.SubElement(types, "Override", {"PartName": f"/xl/worksheets/sheet{i}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
            archive.writestr("[Content_Types].xml", ET.tostring(types, encoding="utf-8", xml_declaration=True))
    return _publish_new(path, write)


def suggest_fields(document: object, limit: int = MAX_FIELDS) -> list[str]:
    """Suggest field paths from a *fetched* sample, without network or guesses.

    Examines the first array element only. Avoid cross-joining unrelated arrays;
    the UI asks the user to confirm/adjust candidates before a new fetch.
    """
    candidates: list[str] = []
    repeating_prefix: str | None = None

    def walk(node: object, path: str, depth: int) -> None:
        nonlocal repeating_prefix
        if len(candidates) >= limit or depth > 6:
            return
        if isinstance(node, dict) and node:
            for key, value in node.items():
                if (not isinstance(key, str) or not key or
                        any(ch in key for ch in ".[]= \t\n\r") or len(key) > 60):
                    continue
                child = path + "." + key if path else key
                walk(value, child, depth + 1)
        elif isinstance(node, list) and node:
            prefix = path + "[*]"
            if "[*]" in path:  # the first version cannot join nested arrays
                return
            if repeating_prefix is None:
                repeating_prefix = prefix
            if repeating_prefix != prefix:
                return
            walk(node[0], prefix, depth + 1)
        elif path and len(path) <= 70:
            if "[*]" not in path or path.startswith(repeating_prefix or ""):
                candidates.append(path)

    walk(document, "", 0)
    return [f"{candidate} = {candidate}" for candidate in candidates[:limit]]
