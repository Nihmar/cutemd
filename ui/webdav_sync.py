"""WebDAV synchronisation."""

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

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
                "PROPFIND", url,
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
        """Return (ok, {relpath: metadata}) for every file on the server.

        If *ok* is False the remote listing failed and the dict is empty.
        The caller must honour the flag.
        """
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

            raw_entries.append((raw, entry))
            if dir_href is None and entry["is_dir"]:
                # Compare decoded paths against the request URL to
                # reliably identify the current directory, since
                # WebDAV servers do not guarantee response ordering.
                href_path = unquote(urlparse(href.text).path).rstrip("/")
                req_path = unquote(urlparse(url).path).rstrip("/")
                if href_path == req_path:
                    dir_href = raw

        if not raw_entries:
            return

        if dir_href is None:
            # The request URL didn't appear in any response entry.
            # This should never happen with a well-behaved server;
            # bail out rather than guessing the wrong directory.
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
            name = unquote(raw[len(prefix) :])
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
        """PROPFIND Depth:0 on a single file, returning its mtime in ns.
        Returns 0 if the request fails or the mtime is unreadable."""
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
    """Parse a WebDAV Last-Modified string into an aware datetime, or None."""
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _mtime_ns_from_datetime(dt: datetime | None) -> int:
    """Convert a datetime to integer nanoseconds since epoch.

    Uses pure integer arithmetic (timedelta fields) to avoid the
    float-precision loss that ``int(dt.timestamp() * 1e9)`` would
    suffer at current epoch values (~1.7e18 ns > 2^53).
    """
    if dt is None:
        return 0
    delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _to_sec_ns(ns: int) -> int:
    """Round nanosecond timestamp down to whole-second precision.

    Remote (WebDAV) mtimes typically have 1-second resolution.
    Normalising to second boundaries prevents false "remote changed"
    detections caused by the precision mismatch with local files.
    """
    return (ns // 1_000_000_000) * 1_000_000_000


def _set_file_mtime(path: Path, remote_mtime: datetime | None) -> None:
    if remote_mtime is None:
        return
    ns = _mtime_ns_from_datetime(remote_mtime)
    os.utime(path, ns=(ns, ns))


def _load_sync_state(local_root: Path) -> dict[str, int]:
    """Load sync state, returning {relpath: last_known_mtime_ns}.

    Values are integer nanoseconds since epoch.
    Returns an empty dict if the file is missing or corrupted.
    """
    path = local_root / ".cutemd" / "sync_state.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result: dict[str, int] = {}
            for k, v in data.items():
                v = int(v)
                # Detect old format (float seconds, ~1.7e9) vs new
                # format (integer nanoseconds, ~1.7e18).  Values
                # below 10^12 are definitely seconds.
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
    """Align local mtime to the server's value after a successful upload.

    Apache mod_dav (OpenMediaVault, etc.) ignores the client's mtime
    during a PUT and assigns the server's current time.  If we kept the
    local mtime in the sync state, the next PROPFIND would report a
    different value (the server-assigned one) and trigger a false
    remote-changed → re-download loop.

    We PROPFIND the just-uploaded file, read the actual server mtime,
    and align both the local file's mtime and the sync state to it.
    """
    server_ns = client.get_remote_mtime_ns(rel)
    if server_ns > 0:
        os.utime(local_file, ns=(server_ns, server_ns))
        new_state[rel] = server_ns
    else:
        # Fallback: server mtime unreadable (rare).  A one-time
        # upload→download cycle may happen on the next sync.
        new_state[rel] = local_ns


def _save_sync_state(local_root: Path, state: dict[str, int]) -> None:
    """Atomically write the sync-state file.

    Uses a temp file + rename to prevent corruption on crash or
    disk-full.
    """
    dotdir = local_root / ".cutemd"
    dotdir.mkdir(parents=True, exist_ok=True)
    real = dotdir / "sync_state.json"
    tmp = dotdir / "sync_state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, real)  # atomic on modern OSes


def sync_folder(
    local_root: Path,
    webdav_url: str,
    username: str,
    password: str,
    progress_callback: Callable[[str], None] | None = None,
) -> SyncResult:
    """Synchronise a local folder with a WebDAV server.

    The algorithm uses integer nanosecond timestamps throughout to
    avoid floating-point precision issues.  Remote mtimes are
    normalised to second boundaries (WebDAV servers rarely support
    sub-second precision).  On the very first sync (empty local
    state) the code bootstraps by recording the remote timestamp as
    the baseline instead of blindly uploading or downloading
    everything.
    """
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
    ok, remote = client.list_files()
    if not ok:
        result.errors.append("Remote listing failed — aborting sync")
        return result

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
    new_state: dict[str, int] = dict(sync_state)
    all_paths = set(remote.keys()) | set(local_entries.keys()) | set(sync_state.keys())

    if progress_callback:
        progress_callback("Synchronising...")

    all_items = sorted(all_paths)
    total = len(all_items)

    for idx, rel in enumerate(all_items, 1):
        local_file = local_entries.get(rel)
        remote_info = remote.get(rel)

        # ── directories ──────────────────────────────────────────
        if remote_info and remote_info.get("is_dir"):
            if not local_file:
                (local_root / rel).mkdir(parents=True, exist_ok=True)
            continue

        # ── gather timestamps (integer nanoseconds) ───────────────
        local_ns = local_file.stat().st_mtime_ns if local_file else 0
        remote_dt = remote_info.get("lastmodified") if remote_info else None
        remote_ns = _mtime_ns_from_datetime(remote_dt)
        recorded = sync_state.get(rel, 0)

        # ── neither side has the file ────────────────────────────
        if not local_file and not remote_info:
            if rel in sync_state:
                del new_state[rel]
                result.deleted.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Deleted       {_fmt_rel(rel)}")
            continue

        # ── first time seeing this path (bootstrap) ──────────────
        if recorded == 0:
            if local_file and remote_info:
                # Both sides exist but we have no history.
                # Bootstrap from the remote mtime to avoid a
                # pointless mass-transfer on first sync.
                # Fall back to local mtime if the server didn't
                # provide a lastmodified timestamp.
                if remote_ns > 0:
                    _set_file_mtime(local_file, remote_dt)
                    new_state[rel] = remote_ns
                else:
                    new_state[rel] = local_ns
            elif local_file:
                # Only local — upload immediately.
                # Create intermediate directories one level at a time
                # (WebDAV MKCOL is not recursive).
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
                    result.errors.append(f"Upload failed: {rel}")
            elif remote_info:
                # Only remote — download immediately.
                local_path = local_root / rel
                local_path.parent.mkdir(parents=True, exist_ok=True)
                if client.download(rel, local_path):
                    _set_file_mtime(local_path, remote_dt)
                    new_state[rel] = remote_ns
                    result.downloaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            f"[{idx}/{total}] Downloaded    {_fmt_rel(rel)}"
                        )
                else:
                    result.errors.append(f"Download failed: {rel}")
            continue

        # ── local only (was synced, now remote deleted) ──────────
        if local_file and not remote_info:
            del new_state[rel]
            local_file.unlink(missing_ok=True)
            result.deleted.append(rel)
            if progress_callback:
                progress_callback(f"[{idx}/{total}] Deleted       {_fmt_rel(rel)}")
            continue

        # ── remote only (was synced, now locally deleted) ────────
        if remote_info and not local_file:
            del new_state[rel]
            client.delete(rel)
            result.deleted.append(rel)
            if progress_callback:
                progress_callback(f"[{idx}/{total}] Deleted remote {_fmt_rel(rel)}")
            continue

        # ── both sides exist — detect changes ────────────────────
        # Local comparison: exact (nanosecond precision).
        # Remote comparison: rounded to seconds because WebDAV
        # servers only expose second-level last-modified dates.
        local_changed = local_ns != recorded
        remote_changed = _to_sec_ns(remote_ns) != _to_sec_ns(recorded)

        if not local_changed and not remote_changed:
            # Nothing changed on either side.
            new_state[rel] = recorded

        elif local_changed and not remote_changed:
            # Only the local file was modified → upload.
            if client.upload(local_file, rel):
                _record_upload(client, local_file, rel, local_ns, new_state)
                result.uploaded.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Uploaded      {_fmt_rel(rel)}")
            else:
                result.errors.append(f"Upload failed: {rel}")

        elif remote_changed and not local_changed:
            # Only the remote file was modified → download.
            if client.download(rel, local_file):
                _set_file_mtime(local_file, remote_dt)
                new_state[rel] = remote_ns
                result.downloaded.append(rel)
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] Downloaded    {_fmt_rel(rel)}")
            else:
                result.errors.append(f"Download failed: {rel}")

        else:
            # Both changed — conflict resolved by newer mtime.
            # When timestamps are tied we skip to be safe.
            if local_ns > remote_ns:
                if client.upload(local_file, rel):
                    _record_upload(client, local_file, rel, local_ns, new_state)
                    result.uploaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            f"[{idx}/{total}] Uploaded      {_fmt_rel(rel)} (conflict)"
                        )
                else:
                    result.errors.append(f"Upload failed (conflict): {rel}")
            elif remote_ns > local_ns:
                if client.download(rel, local_file):
                    _set_file_mtime(local_file, remote_dt)
                    new_state[rel] = remote_ns
                    result.downloaded.append(rel)
                    if progress_callback:
                        progress_callback(
                            f"[{idx}/{total}] Downloaded    {_fmt_rel(rel)} (conflict)"
                        )
                else:
                    result.errors.append(f"Download failed (conflict): {rel}")
            else:
                # Equal mtimes — both sides claim changes, skip.
                new_state[rel] = max(local_ns, remote_ns)
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
