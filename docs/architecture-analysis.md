# CuteMD Architecture Analysis

## 1. Package Boundaries and Import Graph

### 1.1 Package Inventories

#### `core/` (15 files, 1,340 lines total)

| File | Lines | Purpose |
|---|---|---|
| `core/webdav/sync.py` | 672 | WebDAV client + sync engine (pure logic) |
| `core/link_resolution.py` | 202 | Link/wikilink path resolution, anchor mapping |
| `core/dict_manager.py` | 150 | Hunspell dictionary download manager |
| `core/spell_checker.py` | 150 | Optional pyenchant spell checker wrapper |
| `core/folder_settings.py` | 113 | Per-folder .cutemd/ settings read/write |
| `core/updater.py` | 125 | GitHub release check + download logic |
| `core/constants.py` | 72 | Shared extension sets, thresholds, shortcut categories |
| `core/file_utils.py` | 63 | File I/O with encoding detection, recent folders |
| `core/animation_speed.py` | 53 | Animation duration configuration |
| `core/frontmatter.py` | 40 | YAML frontmatter parsing |
| `core/markdown_actions.py` | 33 | Markdown formatting toolbar/context menu items |
| `core/logging.py` | 28 | Centralized debug logging |
| `core/paths.py` | 25 | PyInstaller-aware resource path resolution |
| `core/platform/linux.py` | 47 | Linux-specific paths |

#### `markdown/` (5 files, 664 lines total)

| File | Lines | Purpose |
|---|---|---|
| `markdown/html_builder.py` | 307 | Full HTML document assembly |
| `markdown/document_renderers.py` | 244 | Office/CBZ/EPUB to HTML converters |
| `markdown/image_utils.py` | 113 | Image dimension detection, file index, path fixing |
| `markdown/tools.py` | 76 | Pygments code highlighting, heading IDs |
| `markdown/math_renderers.py` | 30 | KaTeX math rendering rules |

#### `ui/` (49 files, 14,492 lines total)

| File | Lines | Purpose |
|---|---|---|
| `ui/main_window.py` | 2,404 | Main window |
| `ui/settings_dialog.py` | 1,525 | All settings pages |
| `ui/editor_tab.py` | 1,399 | Single editor+preview tab |
| `ui/markdown_completer.py` | 941 | Smart editing auto-completer |
| 45 more files | 8,223 | Dialogs, panels, widgets, workers |

## 2. Module Size and Responsibilities

### `ui/main_window.py` — 2,404 lines

Recommended extractions:
1. `ui/layout_manager.py` (~300 lines)
2. `ui/right_panel_manager.py` (~120 lines)
3. `ui/zen_mode_manager.py` (~120 lines)
4. `ui/sync_controller.py` (~140 lines)
5. `ui/file_operations.py` (~300 lines)
6. `ui/icon_provider.py` (~50 lines)

Would reduce to ~1,200 lines.

### `ui/editor_tab.py` — 1,399 lines

Recommended extractions:
1. `ui/editor_file_io.py` (~230 lines)
2. `ui/scroll_sync.py` (~200 lines)

Would reduce to ~700 lines.

### `ui/settings_dialog.py` — 1,525 lines

Recommended: extract each settings page into class. Extract browse-button pattern.

## 3. Code Duplication

| Issue | Severity | Location |
|---|---|---|
| Duplicate `_on_new` method | BUG | `main_window.py` |
| Duplicate debug log | MINOR | `main_window.py` L1280 |
| Duplicate action dict (2x 29 items) | HIGH | `main_window.py` |
| Browse-button pattern (5x) | MEDIUM | `settings_dialog.py` |
| Markdown parser built twice | LOW | `main_window.py` + `preview_worker.py` |

## 4. Boundary Violations

| File | Violation |
|---|---|
| `core/dict_manager.py` | Module-level Qt import (QObject, QStandardPaths, QThread, Signal) |
| `core/spell_checker.py` | Qt QStandardPaths import |

## 5. Testability

- 15+ modules (~2,250 lines) pure logic — unit-testable
- 21+ modules (~12,500 lines) UI-coupled — need Qt testing
- Fix 2 core/ boundary violations first
