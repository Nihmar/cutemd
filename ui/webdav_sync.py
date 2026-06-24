"""WebDAV synchronisation."""

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

import requests

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_rel(rel_path: str, width: int = 50) -> str:
    """Format a relative path to exactly *width* chars, truncating on the right."""
    lp = len(rel_path)
    if lp > width:
        rel_path = rel_path[: width - 3] + "..."
    return rel_path.ljust(width)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class WebDAVConfig:
    url: str = ""
    username: str = ""
    password: str = ""
    enabled: bool = False


@dataclass
class SyncResult:
    uploaded: list[str] = field(default_factory=list)
    downloaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    conflicts_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# WebDAV HTTP client
# ---------------------------------------------------------------------------

_NS_D_PREFIX = "{DAV:}"
_PROP_FIND_BODY = """<?xml version="1.0" encoding="utf-8"?>
<propfind xmlns="DAV:">
  <prop>
    <getlastmodified xmlns="DAV:"/>
    <getcontentlength xmlns="DAV:"/>
    <resourcetype xmlns="DAV:"/>
  </prop>
</propfind>"""


class WebDAVClient:
    def __init__(self, url: str, username: str, password: str, timeout: int = 15):
        self._base = url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = (username, password)
        self._timeout = timeout
        self._session.headers.setdefault("User-Agent", "CuteMD")

    def test_connection(self) -> tuple[bool, str]:
        url = self._base.rstrip("/") + "/"
        try:
            resp = self._session.request(
                "PROPFIND",
                url,
                data=_PROP_FIND_BODY,
                headers={"Depth": "0"},
                timeout=self._timeout,
            )
            if resp.status_code in (207, 200, 301, 302):
                return True, ""
            return False, f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            return False, str(e)

    def list_files(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        try:
            self._list_files_recursive("", result)
            return result
        except Exception:
            return result

    def _list_files_recursive(self, rel_dir: str, result: dict[str, dict]) -> None:
        url = self._build_url(rel_dir)
        if not url.endswith("/"):
            url += "/"
        resp = self._session.request(
            "PROPFIND",
            url,
            data=_PROP_FIND_BODY,
            headers={"Depth": "1"},
            timeout=self._timeout,
        )
        if resp.status_code not in (207, 200):
            return

        root = ET.fromstring(resp.content)
        raw_entries: list[tuple[str, dict]] = []
        dir_href: str | None = None

        for response in root.findall(f"{_NS_D_PREFIX}response"):
            href = response.find(f"{_NS_D_PREFIX}href")
            if href is None or href.text is None:
                continue
            raw = href.text.rstrip("/") if href.text else ""

            entry: dict = {"is_dir": False, "size": 0, "lastmodified": None}
            propstat = response.find(f"{_NS_D_PREFIX}propstat")
            if propstat is not None:
                prop = propstat.find(f"{_NS_D_PREFIX}prop")
                if prop is not None:
                    rt = prop.find(f"{_NS_D_PREFIX}resourcetype")
                    if (
                        rt is not None
                        and rt.find(f"{_NS_D_PREFIX}collection") is not None
                    ):
                        entry["is_dir"] = True
                    cl = prop.find(f"{_NS_D_PREFIX}getcontentlength")
                    if cl is not None and cl.text is not None:
                        try:
                            entry["size"] = int(cl.text)
                        except ValueError:
                            pass
                    lm = prop.find(f"{_NS_D_PREFIX}getlastmodified")
                    if lm is not None and lm.text is not None:
                        for fmt in (
                            "%a, %d %b %Y %H:%M:%S %Z",
                            "%a, %d %b %Y %H:%M:%S GMT",
                            "%Y-%m-%dT%H:%M:%S%z",
                            "%Y-%m-%dT%H:%M:%SZ",
                        ):
                            try:
                                entry["lastmodified"] = datetime.strptime(
                                    lm.text.strip(), fmt
                                )
                                if entry["lastmodified"].tzinfo is None:
                                    entry["lastmodified"] = entry[
                                        "lastmodified"
                                    ].replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue

            raw_entries.append((raw, entry))
            if dir_href is None and entry["is_dir"]:
                dir_href = raw

        if not raw_entries:
            return

        if dir_href is None:
            dir_href = raw_entries[0][0]

        for raw, entry in raw_entries:
            rel = self._make_rel(raw, dir_href, rel_dir)
            if rel is None or rel == rel_dir or rel in result:
                continue
            result[rel] = entry
            if entry["is_dir"]:
                self._list_files_recursive(rel, result)

    @staticmethod
    def _make_rel(raw: str, dir_href: str, rel_dir: str) -> str | None:
        if raw == dir_href:
            return rel_dir if rel_dir else ""
        prefix = dir_href + "/"
        if raw.startswith(prefix):
            name = unquote(raw[len(prefix) :])
            if rel_dir:
                return rel_dir + "/" + name
            return name
        return None

    def upload(self, local_path: Path, remote_rel: str) -> bool:
        url = self._build_url(remote_rel)
        try:
            with open(local_path, "rb") as fh:
                resp = self._session.put(url, data=fh, timeout=self._timeout)
            return resp.status_code in (200, 201, 204, 207)
        except Exception:
            return False

    def download(self, remote_rel: str, local_path: Path) -> bool:
        url = self._build_url(remote_rel)
        try:
            resp = self._session.get(url, timeout=self._timeout)
            if resp.status_code != 200:
                return False
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as fh:
                fh.write(resp.content)
            return True
        except Exception:
            return False

    def mkdir(self, remote_rel: str) -> bool:
        url = self._build_url(remote_rel)
        try:
            resp = self._session.request("MKCOL", url, timeout=self._timeout)
            return resp.status_code in (201, 200, 405, 301, 302)
        except Exception:
            return False

    def delete(self, remote_rel: str) -> bool:
        url = self._build_url(remote_rel)
        try:
            resp = self._session.delete(url, timeout=self._timeout)
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def _build_url(self, remote_rel: str) -> str:
        if not remote_rel:
            return self._base
        encoded = "/".join(
            requests.utils.quote(segment, safe="") for segment in remote_rel.split("/")
        )
        return f"{self._base}/{encoded}"


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------

_EXCLUDE_DIRS = {".cutemd", ".git", ".svn", "_dav"}


def _set_file_mtime(path: Path, remote_mtime: datetime | None) -> None:
    if remote_mtime is None:
        return
    ts = remote_mtime.timestamp()
    os.utime(path, (ts, ts))


def _load_sync_state(local_root: Path) -> dict[str, float]:
    path = local_root / ".cutemd" / "sync_state.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_sync_state(local_root: Path, state: dict[str, float]) -> None:
    dotdir = local_root / ".cutemd"
    dotdir.mkdir(parents=True, exist_ok=True)
    path = dotdir / "sync_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def sync_folder(
    local_root: Path,
    webdav_url: str,
    username: str,
    password: str,
    progress_callback: Callable[[str], None] | None = None,
) -> SyncResult:
    result = SyncResult()
    client = WebDAVClient(webdav_url, username, password)

    if progress_callback:
        progress_callback("Connecting...")

    ok, err = client.test_connection()
    if not ok:
        result.errors.append(f"Connection failed: {err}")
        return result

    if progress_callback:
        progress_callback("Listing remote files...")
    remote = client.list_files()

    if progress_callback:
        progress_callback("Scanning local files...")
    local_entries: dict[str, Path] = {}
    for p in local_root.rglob("*"):
        if p.is_dir():
            continue
        parts = p.relative_to(local_root).parts
        if parts and parts[0] in _EXCLUDE_DIRS:
            continue
        local_entries[p.relative_to(local_root).as_posix()] = p

    sync_state = _load_sync_state(local_root)
    new_state: dict[str, float] = dict(sync_state)
    all_paths = set(remote.keys()) | set(local_entries.keys()) | set(sync_state.keys())

    if progress_callback:
        progress_callback("Synchronising...")

    all_items = sorted(all_paths)
    total = len(all_items)

    for idx, rel in enumerate(all_items, 1):
        local_file = local_entries.get(rel)
        remote_info = remote.get(rel)

        if remote_info and remote_info.get("is_dir"):
            if not local_file:
                local_dir = local_root / rel
                local_dir.mkdir(parents=True, exist_ok=True)
            continue

        local_mtime = local_file.stat().st_mtime if local_file else 0.0
        remote_mtime_dt = remote_info.get("lastmodified") if remote_info else None
        remote_mtime = remote_mtime_dt.timestamp() if remote_mtime_dt else 0.0
        recorded = sync_state.get(rel, 0.0)

        if not local_file and not remote_info:
            if rel in sync_state:
                del new_state[rel]
                result.deleted.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Deleted {_fmt_rel(rel)}")
            continue

        if local_file and not remote_info:
            if rel in sync_state:
                del new_state[rel]
                local_file.unlink(missing_ok=True)
                result.deleted.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Deleted {_fmt_rel(rel)}")
                continue

            parent_rel = "/".join(rel.split("/")[:-1])
            if parent_rel:
                client.mkdir(parent_rel)
            if client.upload(local_file, rel):
                new_state[rel] = local_mtime
                result.uploaded.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Uploaded {_fmt_rel(rel)}")
            else:
                result.errors.append(f"Upload failed: {rel}")

        elif remote_info and not local_file:
            if rel in sync_state:
                del new_state[rel]
                client.delete(rel)
                result.deleted.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Deleted remote {_fmt_rel(rel)}")
                continue

            local_path = local_root / rel
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if client.download(rel, local_path):
                _set_file_mtime(local_path, remote_mtime_dt)
                new_state[rel] = remote_mtime
                result.downloaded.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Downloaded {_fmt_rel(rel)}")
            else:
                result.errors.append(f"Download failed: {rel}")

        elif local_file and remote_info:
            local_changed = local_mtime > recorded + 0.001
            remote_changed = remote_mtime > recorded + 0.001

            if local_changed and not remote_changed:
                if client.upload(local_file, rel):
                    new_state[rel] = local_mtime
                    result.uploaded.append(rel)
                    if progress_callback:
                        progress_callback(f"[{idx}/{total}] Uploaded {_fmt_rel(rel)}")
                else:
                    result.errors.append(f"Upload failed: {rel}")

            elif remote_changed and not local_changed:
                if client.download(rel, local_file):
                    _set_file_mtime(local_file, remote_mtime_dt)
                    new_state[rel] = remote_mtime
                    result.downloaded.append(rel)
                    if progress_callback:
                        progress_callback(f"[{idx}/{total}] Downloaded {_fmt_rel(rel)}")
                else:
                    result.errors.append(f"Download failed: {rel}")

            elif local_changed and remote_changed:
                if local_mtime > remote_mtime:
                    if client.upload(local_file, rel):
                        new_state[rel] = local_mtime
                        result.uploaded.append(rel)
                        if progress_callback:
                            progress_callback(
                                f"[{idx}/{total}] Uploaded {_fmt_rel(rel)} (conflict)"
                            )
                    else:
                        result.errors.append(f"Upload failed (conflict): {rel}")
                elif remote_mtime > local_mtime:
                    if client.download(rel, local_file):
                        _set_file_mtime(local_file, remote_mtime_dt)
                        new_state[rel] = remote_mtime
                        result.downloaded.append(rel)
                        if progress_callback:
                            progress_callback(
                                f"[{idx}/{total}] Downloaded {_fmt_rel(rel)} (conflict)"
                            )
                    else:
                        result.errors.append(f"Download failed (conflict): {rel}")
                else:
                    new_state[rel] = local_mtime
                    result.conflicts_skipped.append(rel)

            else:
                result.conflicts_skipped.append(rel)

    _save_sync_state(local_root, new_state)

    if progress_callback:
        progress_callback("Done.")

    return result


# ---------------------------------------------------------------------------
# Thread wrapper
# ---------------------------------------------------------------------------


from PySide6.QtCore import QThread, Signal  # noqa: E402


class SyncThread(QThread):
    """QThread that runs sync_folder() in the background."""

    progress = Signal(str)
    finished = Signal(object)

    def __init__(
        self, local_root: Path, url: str, username: str, password: str
    ) -> None:
        super().__init__()
        self._local_root = local_root
        self._url = url
        self._username = username
        self._password = password

    def run(self) -> None:
        result = sync_folder(
            self._local_root,
            self._url,
            self._username,
            self._password,
            progress_callback=lambda msg: self.progress.emit(msg),
        )
        self.finished.emit(result)
