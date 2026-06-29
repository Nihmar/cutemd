"""Export Markdown notes to other formats via pandoc.

Supported formats: HTML (self-contained with theme CSS), PDF, ODT, DOCX.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from core.logging import setup_logging

_LOG = setup_logging("cutemd.exporter")

# ---------------------------------------------------------------------------
# Format definitions
# ---------------------------------------------------------------------------

_EXPORT_FORMATS: dict[str, dict] = {
    "html": {
        "label": "HTML",
        "ext": ".html",
        "args": ["-t", "html5", "--standalone"],
    },
    "pdf": {
        "label": "PDF",
        "ext": ".pdf",
        "args": ["-t", "pdf", "--pdf-engine=xelatex"],
    },
    "odt": {
        "label": "ODT (LibreOffice)",
        "ext": ".odt",
        "args": ["-t", "odt"],
    },
    "docx": {
        "label": "DOCX (Word)",
        "ext": ".docx",
        "args": ["-t", "docx"],
    },
}


def export_formats() -> dict[str, dict]:
    """Return a copy of the supported format metadata."""
    return {k: dict(v) for k, v in _EXPORT_FORMATS.items()}


# ---------------------------------------------------------------------------
# Pandoc availability
# ---------------------------------------------------------------------------


def pandoc_available() -> bool:
    """Return True if pandoc is installed and on PATH."""
    return shutil.which("pandoc") is not None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export(
    input_path: Path,
    output_path: Path,
    fmt: str,
    *,
    css: str | None = None,
) -> None:
    """Export *input_path* (Markdown) to *output_path* in the given format.

    If *css* is provided and the format is ``"html"``, it is injected into
    the standalone HTML output so the result matches the application theme.
    """
    if fmt not in _EXPORT_FORMATS:
        raise ValueError(f"Unknown export format: {fmt!r}")

    cfg = _EXPORT_FORMATS[fmt]
    cmd = ["pandoc", str(input_path), "-o", str(output_path)] + cfg["args"]

    _LOG.debug("export: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        err = result.stderr.strip() or "unknown error"
        raise RuntimeError(f"pandoc failed: {err}")

    # Inject CSS for self-contained HTML export
    if fmt == "html" and css:
        _inject_css(output_path, css)

    _LOG.debug("export: written %s", output_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STYLE_REPLACE = b"</style>"


def _inject_css(path: Path, css: str) -> None:
    """Inject *css* into the standalone HTML document."""
    html = path.read_bytes()
    css_bytes = css.encode("utf-8")
    # Insert our CSS before the closing </style> tag (pandoc inserts a
    # minimal style element in standalone mode).
    if _STYLE_REPLACE in html:
        html = html.replace(_STYLE_REPLACE, css_bytes + _STYLE_REPLACE)
    else:
        # No <style> element — inject one before </head>
        head_close = b"</head>"
        if head_close in html:
            html = html.replace(
                head_close,
                b"<style>\n" + css_bytes + b"\n</style>\n" + head_close,
            )
    path.write_bytes(html)
