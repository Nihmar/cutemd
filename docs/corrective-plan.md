# CuteMD Cleanup & Polish — Corrective Plan

Based on architecture-analysis.md and visual-consistency-analysis.md.

## Phase 1 — Architecture Cleanup (High Impact)

### 1.1 Fix Boundary Violations
- Move `core/dict_manager.py` to `ui/dict_manager.py` (it subclasses QThread, uses QObject/QStandardPaths)
- Remove Qt import from `core/spell_checker.py` — extract `_user_dicts_dir()` to a shared utility or accept Qt dependency via QStandardPaths import at function level

### 1.2 Remove Code Duplication
- Delete duplicate `_on_new` method (BUG — defined twice in `main_window.py`)
- Delete duplicate debug log line (`main_window.py` L1280-1281)
- Replace hardcoded action dicts in `_on_show_shortcuts` and `_on_command_palette` with `self._all_actions`
- Extract browse-button pattern in `settings_dialog.py` into a shared `_browse_relative_path()` helper

### 1.3 Split Large Files
- Extract `_setup_central()` widget creation into `ui/layout_manager.py`
- Extract right panel toggles into `ui/right_panel_manager.py`
- Extract zen mode into `ui/zen_mode_manager.py`
- Extract file operations into `ui/file_operations.py`
- Extract icon provider into `ui/icon_provider.py`
- Extract scroll sync from `editor_tab.py` into `ui/scroll_sync.py`

## Phase 2 — Visual Consistency (Medium Impact)

### 2.1 QSS Cleanup
- Remove duplicate `QToolButton:checked` rule
- Group QToolButton rules together
- Add QPushButton base rule with palette references
- Add `:focus` styling for QPushButton and QToolButton

### 2.2 Fix Hardcoded Colors
- Replace `#e06c75` error color with named constant or palette role
- Fix `link_preview_popup.py` header to use palette
- Fix `pdf_viewer.py` white background
- Fix `preview_styles.css` `#58a6ff` link color to use theme override

### 2.3 Consolidate Inline Styles
- Move panel header styles to `style.qss`
- Move settings hint/field label styles to `style.qss`
- Move `CommandPalette` and `#completerPopup` styles to `style.qss`
- Add `#primaryBtn`, `#secondaryBtn`, `#closeBtn` rules to `style.qss`

## Phase 3 — Accessibility & Polish (Low Impact)

### 3.1 Tooltips
- Add tooltips to PDF viewer buttons and checkboxes
- Add tooltips to welcome dialog buttons

### 3.2 Keyboard Navigation
- Add `:focus` visible indicators
- Add keyboard shortcut to focus file tree

## Phase 4 — DPI Scaling (Future)

- Consider `devicePixelRatio()` for fixed widget sizes
- Increase minimum dialog sizes or make them relative
