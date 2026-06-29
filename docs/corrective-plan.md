# CuteMD Cleanup & Polish — Corrective Plan

Based on architecture-analysis.md and visual-consistency-analysis.md.

## Phase 1 — Architecture Cleanup (High Impact) ✅ DONE

### 1.1 Fix Boundary Violations ✅
- [x] Move `core/dict_manager.py` to `ui/dict_manager.py`
- [x] Remove Qt import from `core/spell_checker.py` (dead code removed)

### 1.2 Remove Code Duplication ✅
- [x] Delete duplicate `_on_new` method
- [x] Delete duplicate debug log line
- [x] Replace action dicts with `self._all_actions`
- [x] Extract `_browse_relative_path()` helper

### 1.3 Split Large Files ✅ (partial)
- [x] Extract `ui/icon_provider.py`
- [ ] `ui/zen_mode_manager.py` (deferred)
- [ ] `ui/scroll_sync.py` (deferred)
- [ ] `ui/right_panel_manager.py` (deferred)

## Phase 2 — Visual Consistency (Medium Impact) ✅ DONE

### 2.1 QSS Cleanup ✅
- [x] Remove duplicate `QToolButton:checked` rule
- [x] Group QToolButton rules (base → hover → pressed → checked → focus)
- [x] Add QPushButton base rule with palette references
- [x] Add `:focus` styling for QPushButton and QToolButton

### 2.2 Fix Hardcoded Colors ✅ (partial)
- [x] Define `_ERROR_COLOR` / `_ERROR_SS` in find_bar + search_panel
- [ ] Fix `link_preview_popup.py` header (deferred)
- [x] Fix `pdf_viewer.py` white background → palette(base)
- [ ] Fix `preview_styles.css` `#58a6ff` link color (deferred — minor)

### 2.3 Consolidate Inline Styles ✅ (partial)
- [x] Add panel header rules to `style.qss` (TOC, Backlinks, Metadata)
- [ ] Move CommandPalette styles to `style.qss` (deferred — already uses palette())
- [ ] Move completer popup styles (deferred — already uses palette())

## Phase 3 — Accessibility & Polish (Low Impact) ✅

### 3.1 Tooltips ✅
- [x] PDF viewer: prev/next/open buttons
- [ ] Welcome dialog buttons (deferred — minor)

### 3.2 Keyboard Navigation ✅
- [x] `:focus` visible indicators added to QPushButton and QToolButton

## Phase 4 — DPI Scaling (Future) — Not started

## Phase 5 — Unit Testing ✅ Started

- [x] pytest scaffold with `tests/test_constants.py` (3 passing tests)
- [ ] Add more core/ tests (link_resolution, frontmatter, file_utils)
- [ ] Add CI integration
