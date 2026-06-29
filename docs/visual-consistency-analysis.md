# CuteMD Visual Consistency Analysis

## 1. QSS / Stylesheet (`ui/style.qss`)

### Duplicate Rule
- `QToolButton:checked` appears twice (lines 147 and 165) — identical copy. Remove one.

### Missing Rules
- `#primaryBtn`, `#secondaryBtn`, `#closeBtn` (welcome dialog) have NO QSS rules — rely on Fusion defaults
- `QPushButton` has NO base rule — only styled inside `#findBar`
- `:focus` pseudo-states absent for QPushButton and QToolButton

### Organization
Well-organized with section comments. Group QToolButton rules together: base → hover → pressed → checked.

## 2. Inline Styles (50 occurrences across 15 files)

### Critical Hardcoded Colors

| File | Color | Issue |
|---|---|---|
| `find_bar.py` | `#e06c75` (error border) | Hardcoded red, won't adapt to themes |
| `search_panel.py` | `#e06c75` | Same red, hardcoded |
| `link_preview_popup.py` | `#3c3c3c` / `#cccccc` header | Broken on light themes |
| `pdf_viewer.py` | `white` background | Jarring on dark themes |

### Good (uses palette)
- `command_palette.py` — all rules use `palette(role)`
- `welcome_dialog.py` — all rules use `palette(role)`
- `markdown_completer.py` — uses `palette(window/mid/base/highlight)`

### Recommended to Move to `style.qss`
- Panel headers (3 files duplicated — `backlinks_panel.py`, `metadata_panel.py`, `toc_panel.py`)
- Settings hint labels
- `CommandPalette` dialog styles
- `#completerPopup` from `markdown_completer.py`
- Welcome dialog button styles (add `#primaryBtn`, `#secondaryBtn`, `#closeBtn`)

## 3. Widget Sizing and Spacing

### Inconsistency
Sidebar toolbar buttons: 36x30, icon 18x18  
Editor toolbar buttons: 30x28, icon 18x18  
Margins: 6 vs 4

### Preview CSS Hardcoded Colors
- Light: `#24292e` text, `#ffffff` bg
- Dark: `#c9d1d9` text, `#0d1117` bg
- Link color `#58a6ff` — never changes with theme

## 4. DPI Scaling

No `setPixelSize` calls — all fonts use `setPointSize()` (DPI-aware).  
But ALL widget sizes are in device pixels — `setFixedSize()`, `setFixedWidth()`, etc. No `devicePixelRatio()` multiplication.

Settings dialog 700x560 may overflow on 1366x768 at 125%+ scaling.

## 5. Accessibility

### Missing Tooltips
- PDF viewer: `_prev_btn`, `_next_btn`, `_open_btn`, `_fit_width_cb`, `_fit_height_cb`
- Welcome dialog: primary/secondary/close buttons

### Keyboard Navigation Gaps
- No shortcut to focus file tree
- No visible `:focus` indicator on QPushButton / QToolButton
- No keyboard hints in welcome dialog recent folders list

## Summary

| Priority | Count |
|---|---|
| Critical (hardcoded colors) | 4 |
| High (consolidate styles) | 6 |
| Medium (tooltips/focus) | 5 |
| Low (DPI scaling) | 3 |
