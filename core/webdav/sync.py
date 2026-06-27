"""Pure WebDAV client + sync engine — no Qt imports."""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

import requests

from core.logging import setup_logging

_LOG = setup_logging("cutemd.sync")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_rel(rel_path: str, width: int = 50) -> str:
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
    unchanged: list[str] = field(default_factory=list)
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

    def test_connection(self) -> tuple[bool, str]:
        url = self._base + "/"
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

    def list_files(self) -> tuple[bool, dict[str, dict]]:
        result: dict[str, dict] = {}
        try:
            self._list_files_recursive("", result)
            return True, result
        except Exception:
            return False, {}

    def _list_files_recursive(self, rel_dir: str, result: dict[str, dict]) -> None:
        url = self._build_url(rel_dir)
        if not url.endswith("/"):
            url += "/"
        resp = self._session.request(
            "PROPFIND", url,
            data=_PROP_FIND_BODY,
            headers={"Depth": "1"},
            timeout=self._timeout,
        )
        if resp.status_code not in (207, 200):
            raise RuntimeError(f"PROPFIND {url} -> HTTP {resp.status_code}")

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
                        dt = _parse_http_datetime(lm.text)
                        if dt is not None:
                            entry["lastmodified"] = dt
                        elif lm.text.strip():
                            _LOG.debug(
                                "PROPFIND %s: unparseable getlastmodified: %r",
                                url,
                                lm.text.strip(),
                            )

            raw_entries.append((raw, entry))
            if dir_href is None and entry["is_dir"]:
                if not rel_dir:
                    dir_href = raw
                else:
                    href_last = unquote(raw.rstrip("/")).rstrip("/").rsplit("/", 1)[-1]
                    rel_last = unquote(rel_dir.rstrip("/")).rstrip("/").rsplit("/", 1)[-1]
                    if href_last == rel_last:
                        dir_href = raw

        if not raw_entries:
            return

        if dir_href is None:
            return

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
            name = unquote(raw[len(prefix):])
            if rel_dir:
                return rel_dir + "/" + name
            return name
        return None

    def upload(self, local_path: Path, remote_rel: str) -> bool:
        url = self._build_url(remote_rel)
        try:
            size = local_path.stat().st_size
            with open(local_path, "rb") as fh:
                resp = self._session.put(
                    url,
                    data=fh,
                    headers={"Content-Length": str(size)},
                    timeout=self._timeout,
                )
            return resp.status_code in (200, 201, 204, 207)
        except Exception:
            return False

    def download(self, remote_rel: str, local_path: Path) -> bool:
        url = self._build_url(remote_rel)
        try:
            resp = self._session.get(url, stream=True, timeout=self._timeout)
            if resp.status_code != 200:
                return False
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    fh.write(chunk)
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

    def get_remote_mtime_ns(self, remote_rel: str) -> int:
        url = self._build_url(remote_rel)
        try:
            resp = self._session.request(
                "PROPFIND", url,
                data=_PROP_FIND_BODY,
                headers={"Depth": "0"},
                timeout=self._timeout,
            )
            if resp.status_code not in (207, 200):
                return 0
            root = ET.fromstring(resp.content)
            for response in root.findall(f"{_NS_D_PREFIX}response"):
                propstat = response.find(f"{_NS_D_PREFIX}propstat")
                if propstat is None:
                    continue
                prop = propstat.find(f"{_NS_D_PREFIX}prop")
                if prop is None:
                    continue
                lm = prop.find(f"{_NS_D_PREFIX}getlastmodified")
                if lm is not None and lm.text:
                    dt = _parse_http_datetime(lm.text)
                    if dt is not None:
                        return _mtime_ns_from_datetime(dt)
                    elif lm.text.strip():
                        _LOG.debug(
                            "get_remote_mtime_ns %s: unparseable: %r",
                            remote_rel,
                            lm.text.strip(),
                        )
        except Exception:
            pass
        return 0

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


def _parse_http_datetime(text: str) -> datetime | None:
    raw = text.strip()
    if not raw:
        return None

    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    _MONTHS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    try:
        rest = raw.split(", ", 1)[1] if ", " in raw else raw
        for suffix in (" GMT", " UTC", "Z"):
            if rest.endswith(suffix):
                rest = rest[: -len(suffix)]
                break
        else:
            for i, ch in enumerate(rest):
                if ch in "+-" and i >= 8:
                    rest = rest[:i]
                    break
        parts = rest.split()
        if len(parts) == 4:
            day = int(parts[0])
            month = _MONTHS[parts[1].strip().lower()[:3]]
            year = int(parts[2])
            h, m, s = map(int, parts[3].split(":"))
            return datetime(year, month, day, h, m, s, tzinfo=timezone.utc)
    except (KeyError, IndexError, ValueError):
        pass

    return None


def _mtime_ns_from_datetime(dt: datetime | None) -> int:
    if dt is None:
        return 0
    delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _to_sec_ns(ns: int) -> int:
    return (ns // 1_000_000_000) * 1_000_000_000


def _set_file_mtime(path: Path, remote_mtime: datetime | None) -> None:
    if remote_mtime is None:
        return
    ns = _mtime_ns_from_datetime(remote_mtime)
    os.utime(path, ns=(ns, ns))


def _load_sync_state(local_root: Path) -> dict[str, int]:
    path = local_root / ".cutemd" / "sync_state.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result: dict[str, int] = {}
            for k, v in data.items():
                v = int(v)
                if v < 1_000_000_000_000:
                    v *= 1_000_000_000
                result[k] = v
            return result
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return {}


def _record_upload(
    client: WebDAVClient,
    local_file: Path,
    rel: str,
    local_ns: int,
    new_state: dict[str, int],
) -> None:
    server_ns = client.get_remote_mtime_ns(rel)
    if server_ns > 0:
        os.utime(local_file, ns=(server_ns, server_ns))
        new_state[rel] = server_ns
    else:
        new_state[rel] = local_ns


def _save_sync_state(local_root: Path, state: dict[str, int]) -> None:
    dotdir = local_root / ".cutemd"
    dotdir.mkdir(parents=True, exist_ok=True)
    real = dotdir / "sync_state.json"
    tmp = dotdir / "sync_state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, real)


def sync_folder(
    local_root: Path,
    webdav_url: str,
    username: str,
    password: str,
    progress_callback: Callable[[str], None] | None = None,
    translate: Callable[[str, str], str] | None = None,
) -> SyncResult:
    """Synchronise a local folder with a WebDAV server.

    Parameters
    ----------
    local_root:
        Root directory of the local notes folder.
    webdav_url, username, password:
        WebDAV connection parameters.
    progress_callback:
        Optional callable for progress messages.
    translate:
        Optional translation function ``(context, message) -> str``.
        Defaults to identity (returns English).

    Returns a ``SyncResult`` dataclass detailing what happened.
    """
    if translate is None:
        translate = lambda ctx, msg: msg

    result = SyncResult()
    client = WebDAVClient(webdav_url, username, password)

    if progress_callback:
        progress_callback(translate("WebDAV", "Connecting..."))

    ok, err = client.test_connection()
    if not ok:
        result.errors.append(translate("WebDAV", "Connection failed: {}").format(err))
        return result

    if progress_callback:
        progress_callback(translate("WebDAV", "Listing remote files..."))
    ok, remote = client.list_files()
    if not ok:
        result.errors.append(translate("WebDAV", "Remote listing failed \u2014 aborting sync"))
        return result

    if progress_callback:
        progress_callback(translate("WebDAV", "Scanning local files..."))
    local_entries: dict[str, Path] = {}
    for p in local_root.rglob("*"):
        if p.is_dir():
            continue
        parts = p.relative_to(local_root).parts
        if parts and parts[0] in _EXCLUDE_DIRS:
            continue
        local_entries[p.relative_to(local_root).as_posix()] = p

    sync_state = _load_sync_state(local_root)
    new_state: dict[str, int] = dict(sync_state)
    all_paths = set(remote.keys()) | set(local_entries.keys()) | set(sync_state.keys())

    if progress_callback:
        progress_callback(translate("WebDAV", "Synchronising..."))

    all_items = sorted(all_paths)
    total = len(all_items)

    for idx, rel in enumerate(all_items, 1):
        local_file = local_entries.get(rel)
        remote_info = remote.get(rel)

        if remote_info and remote_info.get("is_dir"):
            if not local_file:
                (local_root / rel).mkdir(parents=True, exist_ok=True)
            continue

        local_ns = local_file.stat().st_mtime_ns if local_file else 0
        remote_dt = remote_info.get("lastmodified") if remote_info else None
        remote_ns = _mtime_ns_from_datetime(remote_dt)
        recorded = sync_state.get(rel, 0)

        if remote_dt is None and remote_info is not None:
            _LOG.debug(
                "%-40s  no parseable remote mtime \u2014 using recorded=%d",
                rel,
                recorded,
            )
            remote_ns = recorded

        if not local_file and not remote_info:
            if rel in sync_state:
                del new_state[rel]
                result.deleted.append(rel)
                if progress_callback:
                    progress_callback(translate("WebDAV", "[{}/{}] Deleted       {}").format(idx, total, _fmt_rel(rel)))
            continue

        if recorded == 0:
            if local_file and remote_info:
                if remote_ns > 0:
                    _set_file_mtime(local_file, remote_dt)
                    new_state[rel] = remote_ns
                else:
                    new_state[rel] = local_ns
            elif local_file:
                parts = rel.split("/")[:-1]
                for i in range(1, len(parts) + 1):
                    client.mkdir("/".join(parts[:i]))
                if client.upload(local_file, rel):
                    _record_upload(client, local_file, rel, local_ns, new_state)
                    result.uploaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            f"[{idx}/{total}] Uploaded      {_fmt_rel(rel)}"
                        )
                else:
                    result.errors.append(translate("WebDAV", "Upload failed: {}").format(rel))
            elif remote_info:
                local_path = local_root / rel
                local_path.parent.mkdir(parents=True, exist_ok=True)
                if client.download(rel, local_path):
                    _set_file_mtime(local_path, remote_dt)
                    new_state[rel] = remote_ns
                    result.downloaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            translate("WebDAV", "[{}/{}] Downloaded    {}").format(idx, total, _fmt_rel(rel))
                        )
                else:
                    result.errors.append(translate("WebDAV", "Download failed: {}").format(rel))
            continue

        if local_file and not remote_info:
            del new_state[rel]
            local_file.unlink(missing_ok=True)
            result.deleted.append(rel)
            if progress_callback:
                progress_callback(translate("WebDAV", "[{}/{}] Deleted       {}").format(idx, total, _fmt_rel(rel)))
            continue

        if remote_info and not local_file:
            del new_state[rel]
            client.delete(rel)
            result.deleted.append(rel)
            if progress_callback:
                progress_callback(translate("WebDAV", "[{}/{}] Deleted remote {}").format(idx, total, _fmt_rel(rel)))
            continue

        local_changed = local_ns != recorded
        remote_changed = _to_sec_ns(remote_ns) != _to_sec_ns(recorded)

        _LOG.debug(
            "%-40s  local_ns=%d  remote_ns=%d  recorded=%d  "
            "local_changed=%s  remote_changed=%s",
            rel,
            local_ns,
            remote_ns,
            recorded,
            local_changed,
            remote_changed,
        )

        if not local_changed and not remote_changed:
            new_state[rel] = recorded
            result.unchanged.append(rel)

        elif local_changed and not remote_changed:
            if client.upload(local_file, rel):
                _record_upload(client, local_file, rel, local_ns, new_state)
                result.uploaded.append(rel)
                if progress_callback:
                    progress_callback(translate("WebDAV", "[{}/{}] Uploaded      {}").format(idx, total, _fmt_rel(rel)))
            else:
                result.errors.append(translate("WebDAV", "Upload failed: {}").format(rel))

        elif remote_changed and not local_changed:
            if client.download(rel, local_file):
                _set_file_mtime(local_file, remote_dt)
                new_state[rel] = remote_ns
                result.downloaded.append(rel)
                if progress_callback:
                    progress_callback(translate("WebDAV", "[{}/{}] Downloaded    {}").format(idx, total, _fmt_rel(rel)))
            else:
                result.errors.append(translate("WebDAV", "Download failed: {}").format(rel))

        else:
            if local_ns > remote_ns:
                if client.upload(local_file, rel):
                    _record_upload(client, local_file, rel, local_ns, new_state)
                    result.uploaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            translate("WebDAV", "[{}/{}] Uploaded      {} (conflict)").format(idx, total, _fmt_rel(rel))
                        )
                else:
                    result.errors.append(translate("WebDAV", "Upload failed (conflict): {}").format(rel))
            elif remote_ns > local_ns:
                if client.download(rel, local_file):
                    _set_file_mtime(local_file, remote_dt)
                    new_state[rel] = remote_ns
                    result.downloaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            translate("WebDAV", "[{}/{}] Downloaded    {} (conflict)").format(idx, total, _fmt_rel(rel))
                        )
                else:
                    result.errors.append(translate("WebDAV", "Download failed (conflict): {}").format(rel))
            else:
                new_state[rel] = max(local_ns, remote_ns)
                result.conflicts_skipped.append(rel)

    _save_sync_state(local_root, new_state)

    _LOG.debug(
        "Sync result: %d uploaded, %d downloaded, %d deleted, "
        "%d unchanged, %d errors",
        len(result.uploaded),
        len(result.downloaded),
        len(result.deleted),
        len(result.unchanged),
        len(result.errors),
    )

    if progress_callback:
        progress_callback(translate("WebDAV", "Done."))

    return result


# ---------------------------------------------------------------------------
# Backup before sync
# ---------------------------------------------------------------------------


def backup_vault(
    vault_path: Path,
    backup_dir: str,
    progress_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Copy the entire vault to a timestamped backup directory.

    Returns the backup path on success, or None if the backup directory
    doesn't exist.
    """
    dest_root = Path(backup_dir)
    if not dest_root.is_dir():
        _LOG.debug("backup_vault: backup dir does not exist: %s", backup_dir)
        return None

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    dest = dest_root / f"{vault_path.name}_{ts}"
    _LOG.debug("backup_vault: copying %s → %s", vault_path, dest)

    if progress_callback:
        progress_callback(f"Backing up to {dest.name}...")

    try:
        _copy_tree(vault_path, dest)
    except OSError as e:
        _LOG.exception("backup_vault: copy failed")
        if progress_callback:
            progress_callback(f"Backup failed: {e}")
        return None

    if progress_callback:
        progress_callback("Backup complete.")
    return str(dest)


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy *src* to *dst*, skipping ``.cutemd``."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name == ".cutemd":
            continue
        s = src / item.name
        d = dst / item.name
        if item.is_dir():
            _copy_tree(s, d)
        else:
            import shutil
            shutil.copy2(str(s), str(d))
