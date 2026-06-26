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

## Bug: anchor_at_viewport_top() returns None

### Problem

`anchor_at_viewport_top()` always returns `None` for documents with multiple
anchors. Debugging shows `QTextCharFormat.anchorNames()` only finds anchors
at positions 0-1 (the first `<a name="b0">` in the document). All subsequent
anchors (`b1`..`bN`) are invisible to `anchorNames()`.

### Root cause

QTextBrowser's rich text model stores `<a name="...">` anchor names in the
`QTextCharFormat` of the **character at the anchor position**. However, when
multiple empty `<a name="..."></a>` tags are inserted by `render_with_anchors()`,
only the first one survives with its name in the format. Subsequent anchors
lose their names during HTML-to-QTextDocument conversion.

This was NOT a problem in the old code because `_do_preview_scrolled` was
inline in `editor_tab.py` and was called **only when the preview scrollbar
actually changed**. The old code had the exact same `anchorNames()` logic,
but it happened to work because:

1. `scrollToAnchor("bN")` moved the viewport to the correct heading.
2. The anchor `<a name="bN">` was always at the **first character of a block**
   containing the heading text.
3. `cursorForPosition(QPoint(2, 2))` landed on that first character.
4. `anchorNames()` returned the name because the anchor's position matched.

But in `TextBrowserPreview`, the same logic fails because the anchors are
now inside a nested QTextBrowser (`_browser`) wrapped in a `QVBoxLayout`.
The key difference: **the wrapper adds layout overhead** that shifts
coordinates by a few pixels, causing `cursorForPosition(QPoint(2, 2))` to
land on a slightly different position where `anchorNames()` returns empty.

### Why it worked before

In the old code, `self.preview` WAS the QTextBrowser directly (no wrapper).
`cursorForPosition(QPoint(2, 2))` returned a cursor at the exact top-left
of the QTextBrowser's viewport. Now the QTextBrowser is a child of a
`QVBoxLayout` inside `TextBrowserPreview(QWidget)`. Even with
`setContentsMargins(0, 0, 0, 0)`, the internal rendering geometry may differ
by a few pixels, enough to miss the anchor character position.

### Proposed fix

Instead of relying on `anchorNames()` (which is fragile), use the scroll
position ratio to estimate which anchor is visible:

```python
def anchor_at_viewport_top(self) -> str | None:
    sb = self._browser.verticalScrollBar()
    if sb.maximum() <= 0:
        return None
    ratio = sb.value() / sb.maximum()
    # Map ratio → anchor index using known anchor positions from the HTML
    # (stored in a list populated during set_html)
    ...
```

Alternatively, fix the coordinate issue by using `(0, 0)` instead of `(2, 2)`
and scanning more characters per block.

### Test results

```
Simple doc (1 anchor):
  pos=0 anchorNames=['b0']   ← works
  pos=1 anchorNames=['b0']   ← works

Tall doc (50 sections, scrolled to b20):
  cursor lands on block 40 ("Section 20")  ← correct block
  anchorNames() returns [] for all scanned positions  ← BROKEN
  Searching entire doc: only b0 found (positions 0-1)
```

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
