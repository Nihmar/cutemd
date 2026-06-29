# QTextBrowser → QWebEngineView Migration Plan

## Migration Status

**Phase 1 — Feature parity**

| Step | Status | Notes |
|------|--------|-------|
| 1.1 Dependency | ✅ Done | `PySide6.QtWebEngineWidgets` included in `pyside6-addons` (transitive dep of `pyside6>=6.11.1`) |
| 1.2 Widget replacement | ✅ Done | `PreviewWebEngineView(QWebEngineView)` + `PreviewWebEnginePage(QWebEnginePage)`. Temp file loading via `page().load()`. `<base>` tag injection. `LocalContentCanAccessFileUrls`. Context menu suppressed. `AA_ShareOpenGLContexts` in `main.py`. |
| 1.3 Wikilink interception | ✅ Done | `acceptNavigationRequest()` handles copy-code, external URLs, wikilinks. `file_link_clicked` signal preserved. |
| 1.4 Theme CSS injection | ✅ Done | Theme palette colors (Base, Text, Mid) injected as CSS overrides. Preview scrollbar themed via `::-webkit-scrollbar`. |
| 1.5 Scroll sync | ✅ Done | Bidirectional: editor→preview via `scrollIntoView()` `runJavaScript()`, preview→editor via 30fps polling of `window._cutemd_line` + `_cutemd_at_bottom`. Pixel-accurate via cumulative `blockBoundingRect` heights. Cached, invalidated on text changes. |
| 1.6 Image rendering | ❓ Untested | Should work unchanged — absolute `file:///` URLs embedded by `html_builder.py`. |
| 1.7 Syntax highlighting | ❓ Untested | Should work unchanged — Pygments inline styles in generated HTML. |
| 1.8 Math rendering | ❓ Untested | Should work unchanged — `latex2mathml` → CSS-styled HTML spans. |

**Phase 2 — New features**

| Step | Status | Notes |
|------|--------|-------|
| 2.1 Clickable checkboxes | ❌ Not started | JS→Python bridge for `- [ ]` / `- [x]` toggle. |
| 2.2 Footnote navigation | ❌ Not started | Fragment link handling in `acceptNavigationRequest`. |
| 2.3 KaTeX math | ❌ Not started | Inject KaTeX from `resources/katex/`. |

---

## 1. Current Architecture — End-to-End Preview Pipeline

### 1.1 HTML Generation (`markdown/html_builder.py`)

The pipeline is:

1. **Preprocessing** (happens in `EditorTab._update_preview()`):
   - `strip_frontmatter(text)` — removes YAML frontmatter
   - `preprocess_wikilink_images(text)` — converts `![[target]]` to `![alt](target)`
   - `preprocess_wikilinks(text)` — converts `[[target]]` to `[target](target)`, handles `|` display aliases
   - `preprocess_tags(text)` — wraps `#tag` in styled `<span>`

2. **Rendering** (`build_html()` → `render_with_anchors()` → `add_heading_ids()`):
   - Parses with `markdown-it` (commonmark + table + strikethrough + dollarmath plugins)
   - Injects `<a name="bN"></a>` anchors before every block-level element (headings, paragraphs, code fences, blockquotes, lists, tables, hr, math blocks) — **these are the scroll sync anchors**
   - Post-processes with `add_heading_ids()` — adds `id="slug"` to `<h1>`–`<h6>` tags

3. **Image resolution** (`add_img_dimensions()`):
   - Converts relative image paths to absolute `file:///` URLs using a cached vault-wide file index
   - Adds `width` and `height` attributes via the `get_image_size` callback (QImage-based)

4. **Post-processing**:
   - `fix_image_paragraphs()` — removes margins from `<p>` tags wrapping images
   - `_fix_table_tag()` — adds `border="1"` to all `<table>` tags
   - `_IMG_FILE_URL_RE.sub()` — wraps `<img src="file://...">` in `<a href="file://...">` for click-to-open
   - `_inject_copy_buttons()` — inserts `<a href="http://cutemd-copy/BASE64">` before `<pre><code>` blocks

5. **Document wrapper**:
   ```html
   <!DOCTYPE html>
   <html>
   <head>
     <meta charset='utf-8'>
     <style>{font_body_css} {preview_css}</style>
   </head>
   <body class='dark'|'light'>
     {body_html}
   </body>
   </html>
   ```

### 1.2 Preview Rendering Flow

```
EditorTab._on_text_changed()
  → debounce timer (150ms / 500ms)
  → EditorTab._update_preview()
    → preprocess text
    → send params via signal to PreviewWorker (QThread)
    → PreviewWorker._do_render()
      → build_html() with cloned markdown-it parser
      → emit result_ready(html)
    → EditorTab._on_preview_ready()
      → preview.setHtml(html)
      → compute _line_anchor_map (line → anchor index mapping)
      → _sync_preview_scroll() → preview.scrollToAnchor(anchor)
```

Key state fields:
- `_preview_busy` / `_preview_pending` — skip redundant renders during rapid typing
- `_last_rendered_hash` — detect identical content to avoid re-rendering
- `_last_anchor` — most recent editor-scroll anchor, used for re-sync after render

### 1.3 Scroll Sync (Bidirectional)

**Editor → Preview** (`_on_editor_scrolled`):
1. Get `firstVisibleBlock()` → find its block number
2. Offset by `_frontmatter_offset` (lines removed by frontmatter stripping)
3. Look up in `_line_anchor_map[line]` → get anchor index `N`
4. Call `preview.scrollToAnchor(f"b{N}")`

**Preview → Editor** (`_do_preview_scrolled`):
1. Get cursor at viewport top-left `QPoint(2, 2)`
2. Walk up to 5 QTextDocument blocks backward looking for `charFormat().anchorNames()`
3. If an anchor name `bN` is found, reverse-map to editor line via `_line_anchor_map`
4. Adjust for `_frontmatter_offset`
5. `editor.verticalScrollBar().setValue(ratio * max_ed)`

**Sync guard**: `_syncing_scroll` counter prevents feedback loops (incremented before scroll, decremented after).

**Re-sync after render**: `_pending_sync_anchor` is set to the last anchor, retried up to 10 times with `QTimer.singleShot(0)` if the scrollbar isn't ready yet.

### 1.4 Wikilink / Link Interception

`PreviewTextBrowser` (subclass of `QTextBrowser`):
- `setOpenLinks(False)` — QTextBrowser won't navigate on clicks
- `anchorClicked` signal → `_on_anchor_clicked(url)`:
  - `http://cutemd-copy/BASE64` → decode, copy to clipboard
  - `http://` / `https://` / `www.` → `QDesktopServices.openUrl(url)`
  - Local/file targets → `self.file_link_clicked.emit(target)`
  - `file_link_clicked` signal → `MainWindow._on_file_link_clicked()` which opens in a tab (or creates missing file)

Image clicks: images are wrapped in `<a href="file:///path">`, so clicking an image opens it externally via the URL handler.

### 1.5 Theme CSS Injection

- `ui/preview_styles.css` is read once at startup in `MainWindow.__init__()` as `self._preview_css`
- Passed to each `EditorTab` constructor → held as `self._preview_css`
- Injected into the generated HTML via `build_html()` as a `<style>` tag in `<head>`
- Font family + size are also inlined as `<style>body { font-family: ...; font-size: Npt; }</style>`
- Theme class: `<body class='dark'>` or `<body class='light'>`

All CSS is standard (no `-qt-` prefixed properties). The `preview_styles.css` uses `body.light` / `body.dark` selectors to scope theme colors.

### 1.6 Image Rendering

Two image loading paths work in parallel:

1. **Primary**: `add_img_dimensions()` (in `html_builder.py`) resolves local image paths → absolute `file:///` URLs embedded directly in `<img src="file:///absolute/path">`. This is the main path and handles 99% of images.

2. **Fallback**: `PreviewTextBrowser.loadResource()` override handles any remaining relative URLs via `QTextDocument.ImageResource`. This is a safety net.

QImage-based size detection happens in `get_image_size()` (defined in `preview_browser.py`), called from `add_img_dimensions()`.

### 1.7 Code Highlighting

Pygments generates inline `<span style="color:...">` HTML with the `noclasses=True` formatter. This HTML is embedded directly in the output and requires no external CSS. QTextBrowser only sees the styled spans.

### 1.8 Math Rendering

- `dollarmath` markdown-it plugin detects `$inline$` and `$$block$$` math
- Custom renderers in `markdown/math_renderers.py` use `latex2mathml` to convert LaTeX to MathML, then `_mathml_to_html()` converts MathML to styled HTML (no actual MathML tags — everything is `<span>` / `<i>` with CSS classes like `math-var`, `math-frac`, etc.)
- Fallback: if MathML conversion fails, raw LaTeX is wrapped in `<pre class="math-block-fallback">` or `<span class="math-inline-fallback">`
- CSS for math is in `preview_styles.css` under the `math-*` classes

Note: The KaTeX library files exist in `resources/katex/` but are **not currently used** by the preview pipeline. They were added for potential future use (Phase 2.3).

### 1.9 Binary/Office Document Preview

For DOCX, XLSX, PPTX, CBZ, EPUB, CSV, etc.:
- `AsyncDocRenderer` (QThread) calls `markdown/document_renderers.py` functions
- Output is full HTML with embedded `<style>` tags
- Displayed via `preview.setHtml(html)` — same QTextBrowser instance

---

## 2. Components and Files Touched — Phase 1

### 2.1 Files that MUST change

| File | Change description |
|------|--------------------|
| `pyproject.toml` | No change needed — `PySide6.QtWebEngineWidgets` and `QtWebEngineCore` are included in `pyside6-addons` which is a dependency of the existing `pyside6>=6.11.1`. Just verify the imports work at runtime (§1.1). |
| `ui/preview_browser.py` | Rewrite: replace `PreviewTextBrowser(QTextBrowser)` with `PreviewWebEngineView(QWebEngineView)` + `PreviewWebEnginePage(QWebEnginePage)`. Includes: `QWebEngineSettings.LocalContentCanAccessFileUrls`, `page().setContent()` (not `setHtml()`), `acceptNavigationRequest()` for link interception, context menu override (Chromium default menu is inappropriate). Keep `get_image_size()` here. |
| `ui/editor_tab.py` | Replace `PreviewTextBrowser` with `PreviewWebEngineView` in imports and instantiation. Rewrite scroll sync logic (`_on_editor_scrolled`, `_do_preview_scrolled`, `_sync_preview_scroll`) to use `runJavaScript()`. Update `set_preview_visible()` if needed. Update font zoom mechanism. Update event filter on `_preview_viewport`. Add `_preview_scroll_timer` (polling) with start/stop in load cycle. |
| `main.py` | Add `AA_ShareOpenGLContexts` before `QApplication` creation (§3.12). Required for multi-tab stability. |
| `ui/main_window.py` | No direct changes expected — the preview widget is only referenced through `EditorTab`. However, `_on_toggle_preview` and zoom methods will continue to work if the public API is preserved. |
| `ui/preview_worker.py` | No changes expected (runs in QThread, generates HTML string). |
| `markdown/html_builder.py` | Minimal changes — CSS may need minor adjustments for WebEngine's more strict rendering. |
| `scripts/build_windows.bat` | Add `--hidden-import PySide6.QtWebEngineWidgets` and any data files |
| `scripts/build_windows.sh` | Same as above |
| `scripts/build_appimage.sh` | Same as above |

### 2.2 Files that may need minor changes

| File | Reason |
|------|--------|
| `ui/preview_styles.css` | May need adjustments for WebEngine CSS rendering differences |
| `markdown/document_renderers.py` | Output is HTML displayed in the same preview — should work, but verify |
| `ui/async_doc_renderer.py` | Calls `self.preview.setHtml()` — must change to `preview.page().setContent(html.encode(), "text/html;charset=utf-8", base_url)` |
| `ui/link_preview_popup.py` | Uses its own `QTextBrowser` internally — does NOT need to change |
| `ui/settings_applicator.py` | Passes preview font settings to tabs — should work if API preserved |

### 2.3 Files NOT touched

- `markdown/tools.py` — Pygments rendering, no Qt dependency
- `markdown/math_renderers.py` — pure text → HTML, no Qt dependency
- `markdown/image_utils.py` — path resolution logic, no Qt dependency
- `core/link_resolution.py` — path resolution, no Qt dependency
- `core/constants.py` — constants only
- `ui/link_manager.py` — editor-side link detection, not preview-side
- `ui/markdown_completer.py` — editor autocomplete, unrelated
- `ui/preview_worker.py` — only generates HTML strings in QThread

---

## 3. Detailed Implementation Strategy — Phase 1

### 3.1 Dependency

No new dependencies are needed. Both `PySide6.QtWebEngineWidgets` (for `QWebEngineView`,
`QWebEnginePage`) and `PySide6.QtWebEngineCore` (for `QWebEngineSettings`) are included
in `pyside6-addons`, which is already a transitive dependency of `pyside6>=6.11.1`.

Runtime fallback: if the import fails (e.g., on a headless system without WebEngine
support), show a `QMessageBox.critical()` and fall back to QTextBrowser or exit
gracefully.

### 3.2 Widget Replacement (`ui/preview_browser.py`)

Create new classes:

```python
class PreviewWebEnginePage(QWebEnginePage):
    """Custom QWebEnginePage that intercepts navigation requests."""
    file_link_clicked = Signal(str)  # target path
    copy_code = Signal(str)          # decoded code to copy
    
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        url_str = url.toString()
        
        # Copy-code interception
        if url_str.startswith("http://cutemd-copy/"):
            payload = url_str.removeprefix("http://cutemd-copy/")
            decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(decoded)
            return False
        
        # External URLs → system browser
        if url_str.startswith(("http://", "https://", "www.")):
            QDesktopServices.openUrl(url)
            return False
        
        # Local file/image paths
        target = url.toLocalFile() if url.isLocalFile() else url_str
        if target:
            self.file_link_clicked.emit(target)
        return False  # Block all navigation


class PreviewWebEngineView(QWebEngineView):
    """QWebEngineView replacement for PreviewTextBrowser."""
    file_link_clicked = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = PreviewWebEnginePage(self)
        self.setPage(self._page)
        self._page.file_link_clicked.connect(self.file_link_clicked)
        self._base_dir: Path | None = None
        self._attachments_dir: Path | None = None
    
    def set_base_dir(self, d: Path) -> None:
        self._base_dir = d.resolve()
    
    def set_attachments_dir(self, d: Path | None) -> None:
        self._attachments_dir = d.resolve() if d else None
```

**Comments on `get_image_size()`**: This function uses QImage to measure image dimensions. It's called from `html_builder.py` via the `SizeProvider` callback. It doesn't depend on QTextBrowser. Keep it in `preview_browser.py` or move to a utility module. I'll keep it in `preview_browser.py` for minimal diff.

### 3.3 Wikilink Interception

Handled by `PreviewWebEnginePage.acceptNavigationRequest()` as described above. The key difference from QTextBrowser:

| QTextBrowser | QWebEngineView |
|---|---|
| `anchorClicked` signal | `acceptNavigationRequest()` override |
| `setOpenLinks(False)` | Return `False` from `acceptNavigationRequest()` |
| `url.toLocalFile()` for file:// URLs | Same |
| `http://` auto-detection | Same |

The `file_link_clicked` signal is preserved with the same signature so `main_window.py` needs no changes.

### 3.4 Scroll Sync — THIS IS THE TRICKIEST PART

**Problem**: QWebEngineView has no:
- `scrollToAnchor(name)` method
- `cursorForPosition()` API
- `QTextDocument` block/format inspection

Everything must go through JavaScript.

#### 3.4.1 Editor → Preview Scroll Sync

Replace `self.preview.scrollToAnchor(anchor)` with:

```python
def _scroll_preview_to_anchor(self, anchor: str):
    js = f"""
    (function() {{
        var el = document.querySelector('a[name="{anchor}"]');
        if (el) {{
            el.scrollIntoView({{ block: 'start', behavior: 'instant' }});
            return true;
        }}
        return false;
    }})();
    """
    self.preview.page().runJavaScript(js)
```

#### 3.4.2 Preview → Editor Scroll Sync

Replace the cursor-based anchor detection with JavaScript polling.

**Important — anchor detection logic**: we want the **last anchor the user has
scrolled past**, i.e. the one whose top edge is at or above the viewport top.
Iterating anchors in DOM order and picking `rect.top <= 5` gives the correct
result (the last one that has passed the top). Using `rect.top >= 0` would
pick the next anchor *below* the viewport — wrong.

```python
def _find_preview_anchor(self):
    """Ask the preview which anchor (bN) is at the top of its viewport."""
    js = """
    (function() {
        var anchors = document.querySelectorAll('a[name]');
        var best = null;
        anchors.forEach(function(a) {
            var rect = a.getBoundingClientRect();
            if (rect.top <= 5) {
                best = a.getAttribute('name');
            }
        });
        return best || '';
    })();
    """
    self.preview.page().runJavaScript(js, self._on_preview_anchor_found)
```

Since anchors are iterated in DOM order, `best` ends up holding the last
anchor whose `rect.top` is at/below the 5 px threshold — the correct one.

#### 3.4.3 Scroll Sync Architecture Changes

The current code has adaptive retry (`_sync_retries`, `_pending_sync_anchor`, up to 10 retries with `QTimer.singleShot(0)`) because `QTextBrowser` might not have laid out the document immediately. With WebEngine, `runJavaScript()` callbacks execute when the page is loaded, so we get deterministic timing.

New flow for **render → sync**:
1. `_on_preview_ready()` receives the HTML
2. Call `self.preview.page().setContent(...)` — WebEngine loads asynchronously
3. Connect to `self.preview.loadFinished` signal with a one-shot callback (see pattern below)
4. On `loadFinished`, set `_pending_sync_anchor = self._last_anchor`, call `_do_sync_preview_scroll()`

This eliminates the retry loop entirely, since `loadFinished` guarantees the
document is ready.

**One-shot `loadFinished` pattern** — critical to avoid handler accumulation:

```python
def _on_preview_ready(self, html: str) -> None:
    # ... cancel spinner, compute anchor map, etc. ...

    def on_load(ok: bool) -> None:
        # Disconnect immediately so it doesn't fire again on future loads
        self.preview.loadFinished.disconnect(on_load)
        self._syncing_scroll += 1
        self._preview_stack.setCurrentIndex(0)
        self._syncing_scroll -= 1
        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()

    self.preview.loadFinished.connect(on_load)
    base_url = QUrl.fromLocalFile(str(self._base_dir))
    self.preview.page().setContent(
        html.encode("utf-8"), "text/html;charset=utf-8", base_url
    )
```

Without the explicit `disconnect(on_load)`, each `setContent()` call accumulates
a new handler and they all fire on every subsequent load — causing duplicate
scroll syncs and potential race conditions.

#### 3.4.4 Scroll Event Handling

**Editor scroll events**: `editor.verticalScrollBar().valueChanged` → `_on_editor_scrolled()` — same logic, but the scroll call changes to `runJavaScript()` as above.

**Preview scroll events**: QWebEngineView doesn't expose a `verticalScrollBar()` signal. Instead, we inject a JavaScript scroll listener:

```javascript
window.addEventListener('scroll', function() {
    // Communicate scroll position back to Python
    // via QWebChannel or a navigation request to a custom scheme
});
```

**Two approaches for preview→editor scroll notification**:

**Option A — QWebChannel**: 
- Requires `pip install PySide6.QtWebChannel`
- Set up a `QWebChannel` with a handler object
- JavaScript calls the handler on scroll
- More complex but cleaner

**Option B — Custom URL scheme**:
- On scroll, JavaScript sets `window.location.hash = '#scroll-N'` or navigates to `cutemd-scroll://POSITION`
- Intercepted in `acceptNavigationRequest()`
- Very simple, doesn't require QWebChannel setup

**Option C — Polling with a QTimer**:
- Run a periodic QTimer (e.g., every 100ms) that calls `runJavaScript()` to get the current scroll position / visible anchor
- No JavaScript injection needed beyond the one-time query
- Slightly less responsive (100ms lag), but dead simple

**Recommendation**: Start with **Option C (polling)** for Phase 1. It's the simplest and most reliable. We can upgrade to QWebChannel in Phase 2 if needed. The current preview→editor sync already has some lag from the QTextBrowser approach and no one has complained.

Polling implementation:
1. In `__init__`, create a `_preview_scroll_timer = QTimer(self)` with 150ms interval
2. On each tick, run the anchor-finding JS, callback reverse-maps to editor line
3. Start/stop the timer based on preview visibility and whether the preview has focus/hover (to avoid unnecessary polling)

Actually, even simpler: only poll when the preview is being scrolled. We can detect this via the JavaScript scroll handler or just always poll when the preview is visible. For Phase 1, constant polling while `_preview_visible` is fine — 150ms interval with a simple `runJavaScript()` call has negligible overhead.

### 3.5 HTML Delivery — `setContent()` NOT `setHtml()`

**Critical**: `QWebEngineView.setHtml()` silently truncates HTML above **2 MB**. Large notes
or those with base64-embedded images will hit this limit and render incomplete.

The fix is to use `page().setContent()` which has no such limit:

```python
base_url = QUrl.fromLocalFile(str(self._base_dir))
self.preview.page().setContent(
    html.encode("utf-8"), "text/html;charset=utf-8", base_url
)
```

This is an architectural decision to make from the start — do NOT use `setHtml()`.
Every place that currently calls `setHtml()` on the preview must switch to
`page().setContent()`.

For the `build_html()` function, `add_img_dimensions()` already converts all
images to absolute `file:///` URLs, so the base URL is primarily a safety net.

### 3.5.1 `QWebEngineSettings` for `file://` Access

Chromium's security model blocks `file://` URLs loaded from content set via
`setContent()` / `setHtml()`. To allow the preview to display local images,
we must explicitly grant access:

```python
from PySide6.QtWebEngineCore import QWebEngineSettings  # NOT QtWebEngineWidgets!

settings = self.page().settings()
settings.setAttribute(
    QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
)
```

**Critical**: `QWebEngineSettings` lives in `PySide6.QtWebEngineCore`, **not**
`PySide6.QtWebEngineWidgets`. Importing from the wrong module causes an
`ImportError` on startup.

This must be set in the `PreviewWebEngineView.__init__()` constructor before any
content is loaded. Without it, embedded `file:///` image URLs will be blocked
by Chromium regardless of the `baseUrl` parameter.

### 3.6 CSS Verification

The current CSS uses standard CSS3 properties. WebEngine (Chromium-based) will render them more faithfully than QTextBrowser. Potential issues:

1. **`font-family: sans-serif`** — default in QTextBrowser, will work fine in WebEngine
2. **`display: inline-flex`** in `.math-frac` — QTextBrowser's QTextDocument doesn't support flexbox (this rule was silently ignored). WebEngine WILL render it with flexbox, potentially changing the appearance of fractions. → **Fix**: remove `display: inline-flex` and use inline-table or adjust the math rendering approach.
3. **`overflow: auto`** on `<pre>` — QTextBrowser ignores `overflow`, WebEngine will respect it and show scrollbars if needed.
4. **`border-radius`** — works in QTextBrowser, should work in WebEngine.
5. **Table `border-collapse`** — same.

The biggest concern is the math CSS. Since the math HTML is generated as flat `<span>` elements (not MathML), the CSS classes like `math-frac` with flexbox may render very differently. This needs visual verification.

### 3.7 Code Highlighting

Pygments `noclasses=True` generates inline `<span style="color:...">`. This is just HTML text and will work identically in WebEngine.

### 3.8 Copy-Code Button

Currently intercepted in `PreviewTextBrowser._on_anchor_clicked()`. In WebEngine:
- `acceptNavigationRequest()` will see the `http://cutemd-copy/BASE64` URL
- Return `False` to block navigation after copying to clipboard
- Same logic, different interception point

### 3.9 Image Click to Open

Currently images wrapped in `<a href="file:///path">` trigger `file_link_clicked` which opens externally. In WebEngine, links to `file:///` URLs will also be intercepted by `acceptNavigationRequest()` → emit `file_link_clicked` → same behavior.

### 3.10 Detachable Preview

`EditorTab.detach_preview()` moves `_preview_stack` to a standalone `QWidget`. Since `_preview_stack` is a `QStackedWidget` containing the preview widget, this should work unchanged regardless of whether the preview is QTextBrowser or QWebEngineView.

### 3.11 Polling Timer — Must Be Stopped During Page Load

When `setContent()` is called, the page enters a loading state. If the 150ms
polling timer fires during this window, `runJavaScript()` returns an empty
string → `_on_preview_anchor_found` receives `""` → the editor gets synced to
line 0 spuriously.

Fix: stop the timer before `setContent()`, restart in `on_load`:

```python
def _on_preview_ready(self, html: str) -> None:
    self._preview_scroll_timer.stop()  # Stop polling during load

    def on_load(ok: bool) -> None:
        self.preview.loadFinished.disconnect(on_load)
        self._syncing_scroll += 1
        self._preview_stack.setCurrentIndex(0)
        self._syncing_scroll -= 1
        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()
        self._preview_scroll_timer.start()  # Resume polling

    self.preview.loadFinished.connect(on_load)
    self.preview.page().setContent(
        html.encode("utf-8"), "text/html;charset=utf-8", base_url
    )
```

### 3.12 OpenGL Context Sharing — Required Before QApplication

`QWebEngineView` requires shared OpenGL contexts between instances. With
multiple tabs (each having its own `QWebEngineView`), the absence of this
attribute causes non-deterministic crashes, especially on Linux/AMD.

In `main.py`, add **before** creating `QApplication`:

```python
from PySide6.QtCore import Qt
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)
```

This must run once, before any `QWebEngineView` is instantiated.

### 3.13 Font Zoom

Currently `zoom_preview(delta)` changes `_preview_font_size` and triggers a full re-render. With WebEngine, we can use `setZoomFactor()` for instant zoom without re-rendering! But for consistency with the current behavior (where zoom persists as a font size setting), we should keep the re-render approach in Phase 1 and consider optimizations in Phase 2.

---

## 4. Risks and Tricky Areas

### 4.1 Risk: QWebEngineView startup overhead
- QWebEngineView initializes a Chromium renderer process, which has memory and startup overhead (~100-200MB RAM, 1-2 second cold start)
- **Mitigation**: The first tab creation will be slightly slower. Subsequent tabs share the same Chromium process.

### 4.2 Risk: Scroll sync race conditions
- `setHtml()` is asynchronous in WebEngine — the document isn't ready immediately
- `runJavaScript()` calls on an unloaded page may silently fail
- **Mitigation**: Use `loadFinished` signal to gate all JavaScript calls after HTML is set

### 4.3 Risk: CSS flexbox on math fractions
- The `.math-frac { display: inline-flex; }` rule will now actually be honored
- The math fraction HTML (`<span class="math-frac"><span class="math-frac-num">...</span><span class="math-frac-den">...</span></span>`) was designed for QTextBrowser where flexbox was ignored
- **Mitigation**: Remove `display: inline-flex` from the CSS or restructure the math HTML. Will need visual testing.

### 4.4 Risk: Scrollbar differences
- WebEngine has its own scrollbar styling (OS-native, not QStyle-based)
- The preview background color may not match the scrollbar in dark themes
- **Mitigation**: Acceptable for Phase 1, can inject custom scrollbar CSS in Phase 2

### 4.5 Risk: Image loading with file:// URLs
- Chromium's security model restricts file:// access from content loaded via `setContent()`
- **Mitigation**: Setting `LocalContentCanAccessFileUrls` (see §3.5.1) is the documented fix.
  The `baseUrl` parameter alone is NOT sufficient — Chromium still blocks cross-directory
  file:// access without this setting. Must be applied BEFORE any content is loaded.

### 4.6 Risk: Binary document preview
- `AsyncDocRenderer._on_doc_rendered()` calls `self.preview.setHtml(html)` — must change to `page().setContent()` pattern (same as main preview rendering, §3.5).
- **Mitigation**: Use `self.preview.page().setContent(html.encode(), "text/html;charset=utf-8", base_url)` with appropriate `baseUrl`.

### 4.7 Risk: Context menu
- `QTextBrowser` has a standard Qt context menu (Copy, Select All). `QWebEngineView` has
  its own Chromium context menu (Back, Forward, Save page as, Inspect, etc.) which is
  completely out of theme and inappropriate for a Markdown preview.
- **Mitigation**: Override `contextMenuEvent()` in `PreviewWebEngineView` or set a custom
  `QMenu` via `QWebEnginePage`. At minimum, block the default menu entirely or provide
  a minimal one (Copy, Select All). This must be added to `ui/preview_browser.py`.

### 4.8 Risk: PyInstaller bundling
- `PySide6.QtWebEngineWidgets` needs to be explicitly imported for PyInstaller to detect it
- Additional data files: QtWebEngine resources (~80MB)
- **Mitigation**: Add `--hidden-import PySide6.QtWebEngineWidgets` to all build scripts. Test AppImage and Windows builds carefully.

---

## 5. Phase 2 Overview

### 5.1 Clickable Checkboxes (2.1)
- Inject JavaScript that adds click handlers to `- [ ]` and `- [x]` list items
- Toggle the checkbox state in the DOM
- Communicate the change back to Python via `acceptNavigationRequest()` with a custom `cutemd-toggle://` URL scheme containing the line number and new state
- Python side: find the line in the editor, toggle between `- [ ]` and `- [x]`, mark file as modified

### 5.2 Footnote Navigation (2.2)
- Requires markdown-it-footnote plugin (or custom footnote parsing)
- Generate `<a href="#fn-N">` for footnote references and `<a id="fn-N">` for definitions
- Already works with anchor-based navigation if the HTML is generated correctly
- May need `acceptNavigationRequest()` to handle `#fragment` links by scrolling to the element

### 5.4 Fragment Link Handling (pre-requisite for 5.2)

In-page fragment links (`<a href="#slug">`) — used by TOC and footnotes — reach
`acceptNavigationRequest()` as URLs like `file:///vault_root/#slug`. Without
special handling they are treated as file-open requests and silently fail.

Phase 1 doesn't generate such links, but they must be handled before Phase 2's
footnote/toc work. The fix in `acceptNavigationRequest()`:

```python
# Handle in-page fragment links (TOC, footnotes, etc.)
if url.hasFragment() and url.path() in ("", "/", str(self._base_dir)):
    fragment = url.fragment()
    self.page().runJavaScript(
        f'document.getElementById("{fragment}")?.scrollIntoView()'
    )
    return False
```

### 5.5 KaTeX Math (2.3)
- Use the existing `resources/katex/` bundle
- Load `katex.min.css` and `katex.min.js` in the preview HTML
- Option A: inject via `<script>` and `<link>` tags in `build_html()`
- Option B: inject via `QWebEngineView.page().runJavaScript()` after load
- Run KaTeX on `document.querySelectorAll('.math')` elements
- Replace the current `latex2mathml` → manual HTML conversion with proper KaTeX rendering
- The `dollarmath` markdown-it plugin already tags math with `math_inline`/`math_block` token types

---

## 6. Open Questions

1. **QWebChannel requirement**: Should we use QWebChannel for the Phase 1 preview→editor scroll sync, or is polling acceptable? → **Decision: use polling for Phase 1, QWebChannel is Phase 2 optimization.**

2. **Math CSS changes**: The flexbox issue for math fractions needs investigation. → **Decision: test visually after migration, fix in Phase 1 if broken.**

3. **KaTeX in Phase 1 or Phase 2**: The plan puts KaTeX in Phase 2. → **Decision: correct — Phase 1 only verifies existing math rendering doesn't regress.**

4. **Multiple tabs with WebEngine**: Does each tab get its own QWebEngineView? → **Yes, each EditorTab has its own preview widget. Chromium shares a process pool.**

5. **`setHtml` vs `setContent`**: `QWebEngineView.setHtml(html, baseUrl)` has a 2 MB limit and silently truncates. `page().setContent(data, mimeType, baseUrl)` has no limit. → **Decision: use `page().setContent()` everywhere, never `setHtml()`. (§3.5)**

6. **Synchronous `runJavaScript` myth**: `runJavaScript()` is always async in PySide6's QWebEngineView. We must use callback patterns. → **Confirmed, all JS calls will use the callback form: `runJavaScript(js, callback)`. Use `loadFinished` one-shot pattern to gate JS after content load. (§3.4.3)**
