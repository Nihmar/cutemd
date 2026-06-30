# Implementation Log — Performance Roadmap

Branch: `perf/performance-roadmap`

## Commits (ordered)

```
b0db0d0 fix: prevent infinite rehighlight loop in deferred spell check
819f738 fix: guard enable_spell in _add_tab with isVisible()
604bc99 Reapply "perf: debounced spell check — 50ms timer, no background thread"
40c698b Revert "perf: debounced spell check — 50ms timer, no background thread"
4823fd4 perf: debounced spell check — 50ms timer, no background thread
89e7f62 perf: shared VaultScanner — single rglob for tags + file list
52c3f48 Revert "perf: async spell-check via background worker thread"
dfdf830 perf: async spell-check via background worker thread
80a7e2a perf: parallel WebDAV transfers + HTTP connection pooling
5e45f4e perf: Phase 3 — QScroller kinetic scroll + ripgrep search backend
3429229 fix: add explicit Ctrl+Tab / Ctrl+Shift+Tab shortcuts
4c32ad4 fix: reset _preview_initialized on theme change
78e5eb2 perf: Phase 2 — lazy imports, tab sleep, body-only preview patch
d3e4615 perf: Phase 1 quick wins — cache, lazy load, single filesystem walk
```

## Remaining items

(None — all 19 items implemented.)

## Key files modified

| File | What changed |
|------|-------------|
| `core/spell_checker.py` | LRU cache on check(), lazy import enchant |
| `core/vault_scanner.py` | NEW — shared background rglob for tags + file list |
| `core/search_index.py` | NEW — inverted word→file index, queried by SearchPanel for plain-text searches |
| `core/vault_scanner.py` | Feeds SearchIndex during scan, optional SearchIndex param |
| `core/webdav/sync.py` | HTTPAdapter pooling, parallel transfers via ThreadPoolExecutor |
| `markdown/html_builder.py` | loading="lazy" decoding="async" on <img> tags |
| `ui/backlinks_panel.py` | Single rglob instead of two (md + markdown) |
| `ui/editor_tab.py` | freeze/activate_preview, body-only runJavaScript with head-stable hash, QScroller, deferred spell wiring |
| `ui/main_window.py` | Lazy MarkdownIt, Ctrl+Tab shortcuts, VaultScanner integration, SearchIndex wiring, deferred spell |
| `ui/preview_styles.css` | content-visibility:auto for large-document virtual DOM |
| `ui/qss_loader.py` | QSS cache per palette |
| `ui/search_panel.py` | Ripgrep backend, inverted-index pre-filtering, set_search_index() |
| `ui/spell_highlighter.py` | Simplified (logic moved to syntax_highlighter) |
| `ui/syntax_highlighter.py` | First-char short-circuit, deferred theme rehighlight, debounced spell check |
| `ui/tags_panel.py` | Uses VaultScanner instead of own TagScanner thread |

## Notes for resuming

- The `SpellHighlighter` in `spell_highlighter.py` is now a stub (logic in syntax_highlighter._SpellWorker was reverted and replaced with debounced timer).
- `TagScanner` class in `tags_panel.py` is dead code (replaced by VaultScanner).
- `BacklinkScanner` still uses its own rglob — not yet integrated into VaultScanner.
- The deferred spell check uses a 50ms QTimer debounce, NOT a background thread.
- `_rehighlighting_for_spell` flag in syntax_highlighter.py prevents infinite loop.
