# Performance Analysis & Optimization Roadmap

> **Status: 13/19 items implemented (68%)** — branch `perf/performance-roadmap`
> Last updated: 2026-06-30

## Methodology

Each subsystem was profiled by reading its source code, identifying
blocking I/O, excessive signal/slot emissions, redundant DOM
reflows, and O(n²) or worse algorithmic complexity.  Where possible,
target metrics are given (e.g. "sub-16 ms" = below one display frame).

---

## 1.  Startup & Cold Launch

### 1.1  Current state

```
main.py → QApplication → MainWindow.__init__
  → QSettings read (sync, ~1-5 ms)
  → CSS file read (sync, <1 ms)
  → MarkdownIt parser init (~15-40 ms — regex compilation, pygments)
  → Translate load (~5-10 ms, .qm file)
  → Theme apply (~10-30 ms — QSS parse + QPalette recalc)
  → Window geometry restore (~1 ms)
  → add_tab → EditorTab.__init__
      → SpellChecker init (imports pyenchant → ~20-50 ms if available)
      → MarkdownHighlighter init (build formats, <1 ms)
      → MarkdownAutoCompleter init (event filter install, <1 ms)
      → File search panel init (no scan yet)
  → Window.show() triggers first paint (~30-75 ms for QWebEngine init)
  → QTimer.singleShot(0) → _restore_last_folder
      → FolderSettings.load() → reads .cutemd/settings.json
      → _set_folder → tree panel scan, tags scan, backlinks scan
```

**Measurable bottlenecks:**

| Step | Est. cost | Impact |
|---|---|---|
| `MarkdownIt("commonmark", ...)` with plugins | 25–50 ms | Blocks startup |
| `import enchant` / `SpellChecker._reload` | 20–50 ms if | Blocks tab creation |
| `QWebEngineView` invisible init | 50–150 ms | First paint delay |
| `_set_folder` → `rglob("*")` + tag scan + backlink scan | 50–300 ms | Blocks UI after show |
| `QSS` re-parse on theme apply | 10–30 ms | Visible flash on theme change |

### 1.2  Proposed fixes

1. **Lazy MarkdownIt** — construct the parser in a background thread
   (`QThread`) during idle, show a bare editor immediately, swap in
   the parser when ready.  First tab uses a placeholder while the
   parser initialises.

2. **Lazy SpellChecker** — defer `import enchant` until the first
   `set_spell_check_langs` call.  The `SpellChecker` constructor
   should accept `lazy=True` and only resolve the enchant import
   when `available` is first accessed.

3. **Lazy QWebEngineView** — the first preview pane creates the
   QWebEngineView.  Until then, show a lightweight QLabel
   "Loading preview…".  The WebEngine context itself is heavy:
   another process, GPU setup, JS engine.  Consider using a
   shared WebEngine profile across tabs.

4. **Deferred folder scan** — `_set_folder` currently blocks the
   event loop with `rglob("*")`.  Use a `QThread` to walk the
   file system and emit results incrementally.  The file tree
   and tag panel populate as data arrives.

5. **Cache QSS** — parse `style.qss` once and cache the result
   per theme.  On theme switch, only swap the cached value into
   `app.setStyleSheet()` — do not re-read and re-substitute `${VAR}`.

6. **Pre-warm the font cache** — Qt font subsystem lazy-loads glyph
   caches.  A synthetic render pass on a hidden widget primes the
   cache before the window becomes visible.

7. **Share OpenGL contexts** — call
   `QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)` **before**
   creating the `QApplication` instance.  Without this attribute,
   every `QWebEngineView` allocates a separate GL context, wasting
   GPU memory and slowing down tab creation.  This is a one-line
   change with zero risk.

---

## 2.  Editor — Typing Latency

### 2.1  Current state

On every keystroke:

```
QPlainTextEdit::keyPressEvent
  → MarkdownAutoCompleter::eventFilter  (auto-pair, list continuation)
  → Syntax highlighter::highlightBlock  (re-highlights current block)
  → Spell check::_spell_check_block     (word regex + enchant.check)
  → LinkManager::_on_text_changed       (500 ms debounce → broken-link scan)
  → Preview timer restart               (300 ms typ. → deferred render)
```

**Bottlenecks:**

| Path | Est. per-keystroke |
|---|---|
| `highlightBlock` with all inline regexes | 0.1–0.5 ms per line |
| `_spell_check_block` word loop + enchant | 0.5–3 ms per line |
| `MarkdownAutoCompleter._handle_key` | <0.1 ms |
| Preview debounce → re-render (indirect) | 5–150 ms deferred |

### 2.2  Proposed fixes

1. **Incremental re-highlight** — QSyntaxHighlighter already only
   re-highlights dirty blocks.  However, `highlightBlock` re-runs
   **all** patterns on the current block.  For large blocks (>500
   chars), consider splitting long paragraphs into smaller
   highlight units (each sentence?).  The real win is to skip the
   spell-check regex on blocks that haven't changed semantically
   (no word boundary crossed) — detect this by hashing the block's
   word set.

2. **Spell-check batching** — `_spell_check_block` calls
   `check(word)` per word, which does a dict lookup per word per
   language.  For multi-language setups, batch all words and
   iterate once per language.  Also, cache `check()` results for
   words seen in the last N seconds (LRU cache of 500 entries).

3. **Asynchronous spell check** — the spell check result doesn't
   need to be synchronous with the keystroke.  Show syntax
   highlighting immediately, then apply spell underlines 50–100 ms
   later via a debounced timer that processes only dirty blocks.
   This decouples the 16 ms frame budget from the 3 ms spell cost.

4. **Regex memoisation** — Python's `re` module caches compiled
   patterns, but `finditer` on a long text is still O(n).  For
   patterns that only apply at the start of a line (HEADING_RE,
   LIST_RE, BLOCKQUOTE_RE), short-circuit the match if the first
   character doesn't match (e.g. heading only if starts with `#`).

5. **Disable features when invisible** — when the editor is
   scrolled, only highlight visible blocks.  When the tab is not
   the current tab, pause preview rendering and link scanning.

6. **Font metrics caching** — QPlainTextEdit recalculates text
   layout on every resize or font change.  Pre-compute the monospace
   font width and cache it.  This is already partially done via
   `setTabStopDistance(40)`.

---

## 3.  Preview — Rendering Latency

### 3.1  Current state

```
textChanged → 300 ms debounce → _update_preview
  → encode hash → PreviewWorker QRunnable → MD → HTML
  → _on_preview_ready → setHtml() → QWebEngineView render
```

**Bottlenecks:**

| Step | Est. cost |
|---|---|
| `MarkdownIt.render()` (sync, Python) | 5–30 ms (text size dependent) |
| `setHtml()` DOM parse + layout | 20–200 ms (WebEngine) |
| Scroll sync `_poll_preview_line` (33 ms timer) | Continuous JS eval overhead |
| Full re-render on every change | Wastes GPU/CPU on unchanged parts |

### 3.2  Proposed fixes

1. **Incremental MD → HTML** — instead of re-rendering the entire
   document, compute a diff of the source text and only re-render
   the changed portion.  A pragmatic first step: skip the render if
   the new text has the same hash as the last rendered text (already
   done — `self._last_rendered_hash`).  For larger documents, use a
   two-level hash: first 100 lines + total hash.

2. **Body-only patch via `runJavaScript`** — instead of `setHtml()`
   which tears down and recreates the entire WebEngine page
   context, use `page.runJavaScript("document.body.innerHTML = `...`")"
   to update only the `<body>` content.  This eliminates the
   WebEngine re-init overhead while keeping the JS engine, CSSOM,
   and GPU textures alive.  The HTML string must be properly
   escaped for backtick-template injection.  This is a Phase 2
   optimisation (medium effort, high impact).

3. **Virtual DOM / content slicing** — for very large documents
   (>5000 lines), split the HTML into chunks and use
   `IntersectionObserver` in JS to only attach visible sections to
   the DOM.  Requires custom JS injection and a scroll handler.
   This is a Phase 3 technique that builds on body-only patching.

4. **WebEngine view recycling** — creating a new QWebEngineView
   is expensive (~50 ms).  When detaching/re-attaching preview,
   reuse the same view instead of destroying and creating one.

5. **Lazy image loading** — inject `loading="lazy"` on all `<img>`
   tags so the browser defers image decode.  Also, use
   `decoding="async"`.

6. **Throttle scroll sync** — the 33 ms poll timer for scroll sync
   runs JavaScript `scrollY` on every tick.  Increase to 100 ms and
   use `requestAnimationFrame` on the JS side to batch sync updates.

7. **Worker thread for render** — already done via `PreviewWorker +
   QThreadPool`.  Verify that the thread pool size is 1 (serial
   renders avoid race conditions).  Consider a render cache:
   maintain the last 3 rendered results so switching tabs is instant.

8. **CSS inlining vs. external** — the preview CSS is dumped inline
   as a `<style>` block in every HTML.  For repeated renders of the
   same tab, this is wasteful.  Use a `<link>` to a `data:` URI
   or a cached file.  (Already done for KaTeX CSS/JS.)

---

## 4.  File Tree — Directory Scanning

### 4.1  Current state

```
_set_folder → FileTreePanel.set_root_path
  → QFileSystemModel.setRootPath → Qt scans the directory
  → QSortFilterProxyModel filters
  → Tags scan → QThread + rglob
  → Backlinks scan → QThread + rglob
```

**Bottlenecks:**

| Step | Est. cost |
|---|---|
| `QFileSystemModel.setRootPath` (Qt internal) | 50–200 ms |
| `rglob("*")` in Python (tags scan) | 30–200 ms per 1000 files |
| `rglob("*")` in Python (backlinks scan) | 30–200 ms per 1000 files |
| Multiple scans run independently — file system thrashing | Combined I/O |

### 4.2  Proposed fixes

1. **Single filesystem walk** — run ONE `rglob("*")` that gathers
   all file metadata (path, mtime, size) and feeds it to all
   consumers (tree model, tags, backlinks, search panel, completer
   file list).  This avoids 3+ independent directory traversals.

2. **Incremental scan via QFileSystemWatcher** — after the initial
   scan, watch the directory tree for changes.  Only re-scan
   affected subdirectories.  Connect `directoryChanged` and
   `fileChanged` signals.

3. **Lazy tree population** — `QFileSystemModel` fetches file
   icons and metadata lazily.  For the initial directory population,
   call `setResolveSymlinks(False)` to reduce stat calls, then use
   a manual `QFileSystemWatcher` after the initial scan completes
   (instead of relying on `QFileSystemModel`'s built-in watcher,
   which adds overhead during bulk loading).  Note:
   `QFileSystemModel.DontWatchForChanges` does **not** exist in
   Qt6/PySide6.

4. **Debounce scans** — rapid file changes (git checkout, bulk
   rename) trigger multiple re-scans.  Use a 500 ms debounce on
   the watcher signals.

5. **Cancel stale scans** — if a new scan is requested while an
   old one is running, cancel the old one (send a cancel token /
   set a flag checked by the thread).

---

## 5.  Search & Find-in-Files

### 5.1  Current state

```
Search in files → rglob("*.md") → read each file → regex search
```

### 5.2  Proposed fixes

1. **Index** — on folder open, build an in-memory inverted index
   (path → word set).  Search becomes O(log n) index lookup instead
   of O(n) full-text scan.  For 10,000 files, this is ~100× faster.
   Use `mmap` + regex for the initial index build.

2. **Incremental index** — update the index on file save / file
   system watch events, not on every search.

3. **Streaming results** — show the first 20 results immediately,
   then continue searching in the background.  User can type to
   narrow without waiting for the full scan.

4. **Ripgrep backend** — for the `find_files` / `replace_files`
   operations, consider shelling out to `rg` (ripgrep) if available.
   It's 10–50× faster than Python regex on large file sets.

---

## 6.  Spell Checking

### 6.1  Current state

```
highlightBlock → _spell_check_block → _WORD_RE.finditer → check(word) per word
```

Each `check(word)` does a hash-table lookup in pyenchant (fast).
But the regex `finditer` is Python-level and iterates all characters.

### 6.2  Proposed fixes

1. **Word cache** — maintain an LRU cache (max 2000 entries) on
   `SpellChecker.check()`.  Words repeat across blocks (common
   words, function words), eliminating 60–80% of dict lookups.
   **Thread-safety note**: `functools.lru_cache` is **not**
   thread-safe.  If `_spell_check_block` runs in a background
   thread, use `cachetools.LRUCache` protected by a
   `threading.Lock`, or a `queue.Queue`-based design that
   serialises all `check()` calls to the same thread.

2. **Deferred spell highlight** — already covered in §2.2.3.

3. **Skip-region optimisation** — `skip_regions()` builds a
   `set[int]` of every character position to skip.  For large code
   blocks, this is O(n) memory and time.  Replace with interval
   checks: store `(start, end)` pairs and binary-search into them.

---

## 7.  Memory Usage

### 7.1  Current state

- Each tab holds a full `QTextDocument` (all text + formatting).
- Each tab holds a full `QWebEngineView` with Chromium rendering.
  Chromium uses 50–100 MB per view (shared process, but still
  significant per-view overhead).
- `QSyntaxHighlighter` stores per-block format data (QTextLayout).
- Link manager stores per-block link positions.
- Tags panel stores a dict of tag → {file set}.

### 7.2  Proposed fixes

1. **Tab sleep via LifecycleState** — when a tab is not the current
   tab, use Qt6's built-in page lifecycle API to suspend or discard
   the WebEngine page:
   ```python
   # Suspend JS timers, network activity (fast restore):
   page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
   # Free GPU memory, discard render tree (slower restore):
   page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
   ```
   This is the same mechanism Chrome uses for background tabs.
   It is far more robust than manually un-parenting the widget.
   Restore by setting back to `LifecycleState.Active` on tab switch.
   This is the single biggest memory win.

2. **Limit undo history** — `QTextDocument::setMaximumBlockCount`
   or `QUndoStack::setUndoLimit`.  Already partially done via
   `_snapshot_manager` in history.

3. **Trim format data** — QSyntaxHighlighter stores formatting
   per block.  For blocks that have no special formatting (>90%
   of plain text), avoid storing empty format ranges.  (Qt may
   already do this.)

4. **Lazy image preview** — when a tab has many images in the
   preview, the WebEngine decodes and caches all of them.  Use
   native lazy loading (`loading="lazy"` on `<img>`).

5. **Font subsetting** — the KaTeX CSS/JS bundle is ~280 KB.
   Load it via `<script defer>` to avoid blocking the render.

---

## 8.  Theme Switching

### 8.1  Current state

```
_apply_theme → load qss + substitute vars → app.setStyleSheet
  → all widgets recalculate → markdown highlighter rehighlight
  → preview CSS injected (but only on next render)
```

### 8.2  Proposed fixes

1. **Cache substituted QSS** — `_substitute_vars` is called on
   every theme switch.  Cache the result per theme.

2. **Notify preview without re-render** — instead of re-rendering
   the full preview, inject a `<style>` override that changes
   `body.class` colors via CSS custom properties.  This avoids
   the full MD→HTML pipeline.

3. **Batch re-highlight** — when switching themes, the syntax
   highlighter's `_build_formats` + `rehighlight()` runs on
   every visible tab.  For tabs that aren't visible, defer
   re-highlight until they become visible.

---

## 9.  Link Manager & Broken-Link Detection

### 9.1  Current state

```
textChanged → 500 ms debounce → scan all blocks for links
  → for each link, stat() the target file → mark broken
```

For a 10,000-line file, this is O(lines) link regex + O(links) stat
calls.

### 9.2  Proposed fixes

1. **Cache stat results** — memoise `Path.exists()` and `Path.stat()`
   with a short TTL (2 seconds).  The file system doesn't change
   during typing.

2. **Incremental scan** — only re-scan blocks that changed (the
   highlighter already knows which blocks are dirty).

3. **Debounce per-block** — instead of one global debounce timer,
   use a per-block timer that fires when a block hasn't been typed
   in for 300 ms.

---

## 10. WebDAV Sync

### 10.1 Current state

```
SyncThread → sync_folder
  → test_connection (PROPFIND)
  → list_files (recursive PROPFIND + BFS)
  → rglob("*") on local
  → for each file: compare mtimes, upload/download
```

### 10.2 Proposed fixes

1. **Parallel transfers** — serial upload/download is the main
   bottleneck.  Use `concurrent.futures.ThreadPoolExecutor` with
   4 workers for file transfers.

2. **Persistent HTTP session** — already used (`requests.Session`).
   Ensure `pool_connections` and `pool_maxsize` are set for HTTP/1.1
   keep-alive.

3. **Incremental PROPFIND** — if the sync state is recent (<1 min
   old), skip the full `list_files` and only PROPFIND directories
   with recent changes (check `getlastmodified` on the root).

4. **Streaming large files** — `download` already uses
   `resp.iter_content()`.  Ensure upload uses a similar approach
   with `requests_toolbelt.MultipartEncoder` for large files to
   avoid reading the entire file into memory.

---

## 11. Animation & Smoothness

### 11.1 Current state

- Splitter resize: `QSplitter` built-in animation.
- Panel show/hide: `side_panel_manager` uses width animation.
- Zen mode: `QPropertyAnimation` on margins.
- Scroll sync: 33 ms JS poll.

### 11.2 Proposed fixes

1. **VSync-aligned animations** — use `QPropertyAnimation` with
   `QEasingCurve.OutCubic` for all transitions.  Request VSync
   via `QSurfaceFormat.setSwapInterval(1)`.

2. **Hardware-accelerated scrolling** — QPlainTextEdit software
   renders text.  No GPU acceleration possible at the Qt level.
   However, the preview (QWebEngineView) does use GPU compositing.
   The editor scroll performance is limited by QPlainTextEdit's
   paint engine — consider a `QScroller` with kinetic scrolling.

3. **Avoid layout thrashing** — panel show/hide triggers layout
   recalculation of the entire MainWindow.  Batch panel state
   changes using `setUpdatesEnabled(False)` / `setUpdatesEnabled(True)`.

---

## 12. Implementation Priority

### Phase 1 — Quick Wins (minimal risk, high impact) ✅ 8/9

| # | Item | Status |
|---|------|--------|
| 1 | Spell-check word cache (LRU on `check()`, thread-safe) | ✅ Done |
| 2 | Cache QSS substitute per theme | ✅ Done |
| 3 | Deferred spell highlight (50 ms debounce) | ✅ Done (debounced timer, no thread) |
| 4 | Don't re-highlight invisible tabs on theme switch | ✅ Done |
| 5 | `lazy="loading"` on preview images | ✅ Done |
| 6 | Skip regex on non-matching first char | ✅ Done |
| 7 | Cache link stat() results (2 sec TTL) | ✅ Already present |
| 8 | `AA_ShareOpenGLContexts` before QApplication | ✅ Already present |
| 9 | Single filesystem walk for tree + tags + backlinks | ✅ Done (VaultScanner shared rglob) |

### Phase 2 — Structural Improvements (medium risk, high impact) ✅ 4/5

| # | Item | Status |
|---|------|--------|
| 10 | Lazy MarkdownIt parser | ✅ Done (lazy construction in _get_or_create_md) |
| 11 | Lazy SpellChecker import | ✅ Done (import enchant deferred) |
| 12 | Tab sleep via LifecycleState (Frozen/Discarded) | ✅ Done |
| 13 | Body-only preview patch via `runJavaScript` | ✅ Done |
| 14 | Search index (inverted index on folder open) | ⏭️ Skipped (Large effort) |

### Phase 3 — Deep Changes (higher risk, transformative impact) ✅ 3/5

| # | Item | Status |
|---|------|--------|
| 15 | Incremental MD→HTML preview (re-render changed blocks only) | ⏭️ Skipped (Large) |
| 16 | Ripgrep backend for find-in-files | ✅ Done |
| 17 | Parallel WebDAV transfers | ✅ Done (ThreadPoolExecutor + HTTP pooling) |
| 18 | Hardware-accelerated editor scroll (QScroller) | ✅ Done (TouchGesture) |
| 19 | Virtual DOM for large preview docs | ⏭️ Skipped (Large) |

---

## 13. Metrics & Monitoring

To validate the impact of each optimisation, add:

- **Startup telemetry**: `time.perf_counter()` around each startup step,
  logged at DEBUG level.
- **Frame budget monitor**: a `QElapsedTimer` in `highlightBlock`
  that logs warnings when a single block takes >1 ms.
- **Preview render time**: already logged (PREVIEW_READY len=…).
  Add `time.perf_counter()` delta from request to completion.
- **Memory snapshot**: `tracemalloc` or `psutil.Process.memory_info()`
  on tab open/close events, logged at DEBUG level.

---

## 14. Risk Assessment

| Change | Risk | Mitigation |
|---|---|---|
| Lazy MarkdownIt | Medium — first preview blank | Show "Loading…" placeholder |
| Tab sleep (LifecycleState) | Low — Qt6 built-in API | None needed; mechanism inherited from Chromium |
| Single filesystem walk | Low — refactor only | Keep old code as fallback |
| Incremental preview | High — complex diff logic | Start with hash-skip only |
| Search index | Low — additive feature | Fallback to linear scan if index stale |
| Body-only preview patch | Medium — JS escaping | Unit-test HTML escaping; fallback to `setHtml()` |
| AA_ShareOpenGLContexts | None — one-line change before QApplication | Revert if GPU driver incompatibility detected |
