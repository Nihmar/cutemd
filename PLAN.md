# QTextBrowser Abstraction Plan

## Goal

Wrap the current `QTextBrowser` usage behind an abstract interface (`PreviewWidget`), enabling a future swap to `QWebEngineView` or user-selectable preview engine.

## Architecture

```
PreviewWidget (ABC, QWidget)
  ├── TextBrowserPreview   ← current QTextBrowser implementation
  └── (future) QWebEnginePreview  ← QWebEngineView + JS-based scroll sync
```

## Step 1: Create `ui/preview_widget.py` — ABC

New file with abstract interface:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PreviewWidget(ABC, QWidget):
    """Abstract base for Markdown preview widgets."""

    file_link_clicked = Signal(str)
    scroll_changed = Signal(int)

    @abstractmethod
    def set_read_only(self, v: bool): ...

    @abstractmethod
    def set_open_links(self, v: bool): ...

    @abstractmethod
    def set_open_external_links(self, v: bool): ...

    @abstractmethod
    def set_base_dir(self, d: Path): ...

    @abstractmethod
    def set_attachments_dir(self, d: Path | None): ...

    @abstractmethod
    def set_html(self, html: str): ...

    @abstractmethod
    def set_plain_text(self, text: str): ...

    @abstractmethod
    def scroll_to_anchor(self, anchor: str): ...

    @abstractmethod
    def content_width(self) -> int: ...

    @abstractmethod
    def anchor_at_viewport_top(self) -> str | None:
        """Return anchor name (e.g. 'b3') at the top of the viewport, or None."""
        ...

    @abstractmethod
    def scroll_position(self) -> int: ...

    @abstractmethod
    def max_scroll(self) -> int: ...
```

## Step 2: Create `ui/preview_text_browser.py` — QTextBrowser implementation

Move `PreviewTextBrowser` from `preview_browser.py` to new file, implementing the ABC:

- Wraps `QTextBrowser` inside a `QVBoxLayout`
- `set_html()` → `_browser.setHtml(html)`
- `set_plain_text()` → `_browser.setPlainText(text)`
- `scroll_to_anchor()` → `_browser.scrollToAnchor(anchor)`
- `content_width()` → `_browser.width()`
- `anchor_at_viewport_top()` — moves the block-walking logic from `editor_tab.py:_do_preview_scrolled`
- `scroll_position()` → `_browser.verticalScrollBar().value()`
- `max_scroll()` → `_browser.verticalScrollBar().maximum()`
- `_on_anchor_clicked()` — link routing (copy-code, external, local) stays internal
- `loadResource()` override — image resolution stays internal
- `file_link_clicked` signal emitted from `_on_anchor_clicked()`

## Step 3: Modify `ui/editor_tab.py`

Replace all direct QTextBrowser API calls with abstract interface methods:

| Before | After |
|--------|-------|
| `self.preview.setReadOnly(True)` | `self.preview.set_read_only(True)` |
| `self.preview.setOpenLinks(False)` | `self.preview.set_open_links(False)` |
| `self.preview.setOpenExternalLinks(False)` | `self.preview.set_open_external_links(False)` |
| `self.preview.setHtml(html)` | `self.preview.set_html(html)` |
| `self.preview.setPlainText(text)` | `self.preview.set_plain_text(text)` |
| `self.preview.scrollToAnchor(anchor)` | `self.preview.scroll_to_anchor(anchor)` |
| `self.preview.width()` | `self.preview.content_width()` |
| `self.preview.verticalScrollBar().valueChanged` | `self.preview.scroll_changed` signal |
| `self.preview.verticalScrollBar().maximum()` | `self.preview.max_scroll()` |
| `self.preview.verticalScrollBar().value()` | `self.preview.scroll_position()` |
| `document()` + `cursorForPosition()` block walking | `self.preview.anchor_at_viewport_top()` |

## Step 4: Leave `ui/link_preview_popup.py` untouched

The popup uses a plain `QTextBrowser` (not `PreviewTextBrowser`) with no image loading, no link handling, no scroll sync. No abstraction needed.

## Step 5: Leave `markdown/html_builder.py` untouched

No changes needed.

## Files involved

| File | Action |
|------|--------|
| `ui/preview_widget.py` | **New** — ABC |
| `ui/preview_text_browser.py` | **New** — moved from preview_browser.py |
| `ui/preview_browser.py` | **Delete** (or keep as re-export shim) |
| `ui/editor_tab.py` | **Modify** — use abstract interface |
| `ui/link_preview_popup.py` | No change |
| `markdown/html_builder.py` | No change |

## Risks

### 1. Double QWidget wrapping
`TextBrowserPreview` wraps `QTextBrowser` in a `QVBoxLayout`. `viewport()` must return the browser's viewport, not the wrapper's. `installEventFilter` on viewport must still work.

### 2. Reverse scroll sync becomes async in QWebEngineView
Current `document()` + `cursorForPosition()` is synchronous. QWebEngineView would need `runJavaScript()` callbacks. This is a future problem — TextBrowserPreview keeps the sync approach.

### 3. `loadResource()` fallback lost with QWebEngine
`html_builder.py: add_img_dimensions()` already resolves images to `file://` URLs. The `loadResource()` override is a safety net. With QWebEngineView, this safety net doesn't exist. Verify builder covers 100% of cases.

### 4. `setHtml()` 2 MB limit (QWebEngine only)
QWebEngineView percent-encodes HTML into a data URL. Large documents may exceed 2 MB. Use `setContent()` or temp file as workaround. TextBrowserPreview has no limit.

### 5. Signal routing differs between backends
`anchorClicked` signal (QTextBrowser) vs `acceptNavigationRequest()` override (QWebEngine). Each implementation handles routing internally — the ABC only exposes `file_link_clicked(str)`.

### 6. `content_width()` timing
`width()` may return 0 before first layout. Same risk as before — not introduced by abstraction.

## Verification

Run `uv run main.py` and verify:
- [ ] Preview renders correctly
- [ ] Forward scroll sync (editor → preview) works
- [ ] Reverse scroll sync (preview → editor) works
- [ ] Copy-code buttons work
- [ ] Local images load
- [ ] External links open in browser
- [ ] Local file links emit signal
- [ ] Ctrl+Wheel zoom works on preview
- [ ] Link preview popup still works
