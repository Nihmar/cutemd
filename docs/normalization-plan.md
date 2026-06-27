# CuteMD — Normalization Plan

> Branch `refactor/normalize-architecture` — June 2026

---

## Fase 0 — Preparazione

Prima di iniziare qualsiasi modifica strutturale:

1. **Assicurarsi che non ci siano regressioni funzionali** — non ci sono test automatici, quindi ogni fase va validata manualmente avviando l'app e testando le feature coinvolte.
2. **Commit atomici** — una modifica strutturale per commit, così da poter fare revert mirati.
3. **Non toccare la logica di business** — solo refactoring strutturale. Le feature rimangono identiche.

---

## Fase 1 — Centralizzare le Costanti Condivise

**Obiettivo**: Eliminare le definizioni duplicate di estensioni file, categorie, e path resolution.

### 1.1 Creare `core/constants.py`

Spostare qui TUTTE le costanti duplicate:

```python
# Estensioni file — definite una volta sola
MD_EXTS = frozenset({".md", ".markdown"})
IMG_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"})
PDF_EXTS = frozenset({".pdf"})
DOC_EXTS = frozenset({".docx", ".xlsx", ".pptx", ".cbz", ".epub"})
CSV_EXTS = frozenset({".csv", ".tsv"})

# Altre costanti
LARGE_FILE_THRESHOLD = 1_048_576  # 1 MB
LARGE_FILE_PREVIEW_LINES = 2000
```

### 1.2 Aggiornare tutti i riferimenti

| File da modificare | Riferimenti da sostituire |
|---|---|
| `core/services/link_resolver.py` | `_IMG_EXTS`, `_PDF_EXTS` |
| `ui/editor_tab.py` | `_MD_EXTS`, `_IMG_EXTS`, `_PDF_EXTS`, `_DOC_EXTS`, `_LARGE_FILE_THRESHOLD` |
| `ui/link_preview_popup.py` | `_MD_EXTS`, `_IMG_EXTS`, `_PDF_EXTS`, `_CSV_EXTS`, etc. |
| `markdown/image_utils.py` | `_IMG_EXTS_RE` — adattare a usare `IMG_EXTS` |
| `markdown/document_renderers.py` | `_IMG_EXTS` in `cbz_to_html()` |

### 1.3 Centralizzare le categorie delle shortcuts

Prendere `_SHORTCUT_CATEGORIES` da `shortcuts_dialog.py` e `_CAT_ORDER` da `command_palette.py` e metterle in un unico posto in `core/constants.py`:

```python
SHORTCUT_CATEGORIES = { ... }
CATEGORY_ORDER = { ... }
```

Aggiornare `shortcuts_dialog.py` e `command_palette.py` per importare da lì.

### 1.4 Centralizzare la risoluzione path PyInstaller-aware

Creare `core/paths.py`:

```python
def resolve_path(relative: str) -> Path:
    """Risoluzione path compatibile PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative
```

Aggiornare `main.py`, `ui/theme.py`, `core/desktop_integration.py`, e gli altri.

**✅ Fase 1 completata.** Creati `core/constants.py` e `core/paths.py`. Aggiornati 10 file.

---

## Fase 2 — Consolidare `core/services/`

**Obiettivo**: Eliminare i file da una-funzione.

### 2.1 Unire in `core/file_utils.py`

Accorpare:
- `core/services/file_io.py` → `read_file_with_encoding()`
- `core/services/folder_setup.py` → `default_folder_config()`
- `core/services/recent_folders.py` → `update_recent_folders()`

### 2.2 Rinominare `core/services/link_resolver.py` → `core/link_resolution.py`

Accorpare:
- `core/services/link_resolver.py` → `resolve_link_target()`
- `core/services/anchor_map.py` → `build_line_anchor_map()`

La risoluzione link e la mappatura anchor sono logicamente correlate (entrambe operano su link/struttura documento).

### 2.3 Rimuovere `core/services/__init__.py` e `core/services/`

Dopo il consolidamento, la directory `services/` non serve più.

---

## Fase 3 — Snellire `main_window.py`

**Obiettivo**: Portare `MainWindow` sotto le 800 linee delegando responsabilità a classi helper dedicate.

### 3.1 Estrarre il setup delle azioni e shortcut

Creare `ui/action_registry.py`:

```python
@dataclass
class ActionDef:
    name: str
    text: str
    shortcut: str
    category: str
    checkable: bool = False
    # ...

class ActionRegistry:
    """Centralized registry of all QActions."""
    def __init__(self, parent): ...
    def create_all(self) -> dict[str, QAction]: ...
    def setup_menubar(self, menu_bar, actions): ...
    def connect_shortcuts(self, shortcut_mgr): ...
```

### 3.2 Estrarre la gestione del pannello laterale

Creare `ui/side_panel_manager.py`:

```python
class SidePanelManager(QObject):
    """Gestisce il left stack: tree, search, TOC e le animazioni."""
    def __init__(self, splitter, left_stack, buttons, parent): ...
    def show_tree(self): ...
    def show_search(self): ...
    def show_toc(self): ...
    def hide(self): ...
    def animate_to(self, width): ...
```

### 3.3 Estrarre la gestione finestra

Creare `ui/window_state.py`:

```python
class WindowStateManager:
    """Salva/ripristina geometria, splitter, sessione."""
    def save(self, window): ...
    def restore(self, window): ...
    def save_session(self, tabs): ...
    def restore_session(self) -> bool: ...
```

### 3.4 Estrarre il wiring dei settings

Creare `ui/settings_applicator.py`:

```python
class SettingsApplicator:
    """Applica i cambiamenti dalle impostazioni ai widget."""
    def apply_theme(self, theme_id): ...
    def apply_fonts(self, editor_family, editor_size, preview_family, preview_size): ...
    def apply_to_all_tabs(self, main_window, changes): ...
```

### 3.5 Risultato atteso per `main_window.py`

Dopo l'estrazione, `MainWindow` dovrebbe contenere solo:
- Inizializzazione e wiring dei componenti
- Metodi di alto livello (`_on_open_folder`, `_on_file_link_clicked`, `_on_save`)
- Coordinamento tra i manager estratti

Target: **~600-800 lines**.

---

## Fase 4 — Snellire `editor_tab.py`

**Obiettivo**: Portare `EditorTab` sotto le 600 linee.

### 4.1 Estrarre `LineNumberArea` in un file separato

`ui/line_number_area.py` — è già una classe ben isolata, ma sta inline in `editor_tab.py`.

### 4.2 Estrarre la logica di preview rendering

Creare `ui/preview_manager.py`:

```python
class PreviewManager(QObject):
    """Gestisce il rendering asincrono della preview, debounce, scroll sync."""
    def __init__(self, editor, preview_browser, md_parser, parent): ...
    def schedule_render(self, text, params): ...
    def sync_editor_to_preview(self, line, anchor_map): ...
    def sync_preview_to_editor(self): ...
```

Questo incapsula tutti i flag `_preview_busy`, `_pending_render_hash`, `_syncing_scroll`, `_sync_retries`, `_last_anchor`, `_line_anchor_map`, `_last_rendered_hash` che attualmente sono attributi sparsi in `EditorTab`.

**Beneficio performance**: Il `build_line_anchor_map()` può essere spostato nel worker thread invece di essere eseguito sul main thread.

### 4.3 Estrarre la logica di link detection e highlighting

Creare `ui/link_manager.py`:

```python
class LinkManager(QObject):
    """Rileva link nel testo, gestisce hover, popup, broken link highlights."""
    def __init__(self, editor, parent): ...
    def refresh_highlights(self, text): ...
    def link_at_position(self, pos): ...
    def show_preview(self, path): ...
    def hide_preview(self): ...
```

Questo incapsula `_LINK_RE`, `_WIKILINK_RE`, `_broken_link_selections`, `_hover_link_key`, `_hovered_link_target`, `_link_resolve_cache`, e la logica del `LinkPreviewPopup`.

**Beneficio performance**: `_refresh_link_highlights()` avrà un suo debounce indipendente (500ms) invece di essere chiamato a ogni textChanged.

### 4.4 Estrarre la logica di drag & drop

Creare `ui/drop_handler.py`:

```python
class DropHandler(QObject):
    """Gestisce drag&drop e paste di file/immagini nell'editor."""
    def handle_file_drop(self, path): ...
    def handle_paste(self, mime_data): ...
```

---

## Fase 5 — Snellire `settings_dialog.py`

### 5.1 Estrarre widget riutilizzabili

- `ui/widgets/toggle_switch.py` ← `_ToggleSwitch`
- `ui/widgets/font_picker.py` ← `_FontPicker` + `_FontPreviewDelegate`

### 5.2 Estrarre pagine del dialog

Ogni pagina del settings dialog dovrebbe essere un widget separato:

- `ui/settings/general_page.py`
- `ui/settings/theme_page.py`
- `ui/settings/editor_page.py`
- `ui/settings/preview_page.py`
- `ui/settings/storage_page.py`
- `ui/settings/shortcuts_page.py` — già parzialmente indipendente
- `ui/settings/sync_page.py` — già parzialmente indipendente

Ogni pagina espone metodi `apply()` e `read()` per il dialog principale.

---

## Fase 6 — Eliminare la Duplicazione `ThemeData` ↔ `Theme`

**Obiettivo**: Unire il modello dati tema in un unico posto.

### 6.1 Strategia

Opzione A (consigliata): Spostare TUTTE le definizioni dei temi in `ui/themes.py` e rimuovere `core/theme_data.py`. Non c'è reale necessità di avere dati tema senza Qt — non vengono usati da nessuna parte senza passare da `ui/themes.py`.

Opzione B: Tenere `core/theme_data.py` ma con `ThemeData` che usa `str` per i colori (come ora) e fare in modo che `ui/themes.py` sia solo un wrapper sottile.

**Raccomandazione**: Opzione A. I ~200 byte di QColor non sono un problema di dipendenza.

---

## Fase 7 — Ottimizzazioni di Performance

### 7.1 Cachare `build_file_index()` in `build_html()`

```python
# In ui/preview_manager.py o in un nuovo core/file_index.py
class FileIndexCache:
    def __init__(self, vault_root: Path):
        self._root = vault_root
        self._index: dict[str, list[Path]] = {}
        self._mtime: float = 0
    
    def get(self) -> dict[str, list[Path]]:
        # Invalidato solo se cambia la struttura directory
        root_mtime = self._root.stat().st_mtime
        if root_mtime > self._mtime:
            self._index = build_file_index(self._root)
            self._mtime = root_mtime
        return self._index
```

### 7.2 Cachare `_gnome_animations_enabled()`

```python
_GNOME_ANIMATIONS_CACHE: bool | None = None

def animation_duration_ms(base_ms: int = 150) -> int:
    global _GNOME_ANIMATIONS_CACHE
    factor = _detect_factor()
    # ...
```

La funzione `_detect_factor()` già cachava il risultato di KDE ma non di GNOME.

### 7.3 Cachare le icone colorate

```python
# In MainWindow o in un icon provider
_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}

def _make_colored_icon(self, name: str, color: QColor, size: int = 18) -> QIcon:
    key = (name, color.name(), size)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = self._render_icon(name, color, size)
    return _ICON_CACHE[key]
```

### 7.4 Debounce separato per broken link highlights

```python
# In LinkManager
self._broken_link_timer = QTimer()
self._broken_link_timer.setSingleShot(True)
self._broken_link_timer.setInterval(500)  # 500ms dopo l'ultimo textChanged
self._broken_link_timer.timeout.connect(self._refresh_link_highlights)
```

### 7.5 Spostare `build_line_anchor_map()` nel worker thread

Attualmente viene chiamata nel main thread a ogni textChanged. Può essere calcolata nel `PreviewWorker` insieme al rendering HTML, dato che il parsing markdown-it deve comunque essere eseguito.

```python
# In PreviewWorker._do_render()
def _do_render(self, params):
    text = params["text"]
    html = build_html(**params)
    anchor_map = build_line_anchor_map(self._md, text)
    self.result_ready.emit(html, anchor_map)
```

### 7.6 Filtro regex pre-compilato per il syntax highlighter

`MarkdownHighlighter.highlightBlock()` applica 9 pattern a ogni linea. Su file grandi, limitare l'highlight alle linee visibili:

```python
def highlightBlock(self, text):
    # Skip if this block is far outside the visible area
    if self._document_large and not self._is_block_visible(block):
        return
```

---

## Fase 8 — Normalizzazioni Minori

### 8.1 Uniformare il logging

`ui/preview_browser.py` deve usare `core.logging.setup_logging` invece di `logging.getLogger`.

### 8.2 Rimuovere `_resolve_path_in_bundle` da `desktop_integration.py`

Usare `core/paths.py:resolve_path()`.

### 8.3 Spostare `core/desktop_integration.py` in `core/platform/linux.py`

Non è logica core usata su tutte le piattaforme.

### 8.4 Rinominare `ui/theme.py` → `ui/qss_loader.py`

Per evitare confusione con `ui/themes.py` (che contiene i temi veri e propri).

---

## Fase 9 — Rivedere i Confini dei Package

### Stato attuale
```
core/          — no Qt ✅
markdown/      — no Qt ✅
ui/            — Qt ✅
```

### Stato proposto
```
core/
  constants.py         — costanti condivise
  paths.py             — risoluzione path (PyInstaller)
  file_utils.py        — I/O, encoding, folder config, recent folders
  link_resolution.py   — risoluzione link + anchor map
  logging.py           — (invariato)
  folder_settings.py   — (invariato)
  animation_speed.py   — (invariato, con cache GNOME)
  updater.py           — (invariato)
  platform/
    linux.py           — (ex desktop_integration.py)
  webdav/
    sync.py            — (invariato)

markdown/              — (invariato, tranne riferimenti a constants.py)

ui/
  main_window.py       — snellito (≤800 lines)
  action_registry.py   — nuovo
  side_panel_manager.py — nuovo
  window_state.py      — nuovo
  settings_applicator.py — nuovo

  editor_tab.py        — snellito (≤600 lines)
  line_number_area.py  — nuovo (estratto)
  preview_manager.py   — nuovo (estratto)
  link_manager.py      — nuovo (estratto)
  drop_handler.py      — nuovo (estratto)

  preview_browser.py   — (logging fix)
  preview_worker.py    — (anchor_map nel thread)
  syntax_highlighter.py — (ottimizzato)

  themes.py            — (incorpora core/theme_data.py)
  theme_manager.py     — (invariato)
  qss_loader.py        — (ex theme.py)

  settings_dialog.py   — snellito (≤200 lines)
  settings/
    general_page.py    — nuovo
    theme_page.py      — nuovo
    editor_page.py     — nuovo
    preview_page.py    — nuovo
    storage_page.py    — nuovo
    shortcuts_page.py  — nuovo
    sync_page.py       — nuovo

  widgets/
    toggle_switch.py   — nuovo
    font_picker.py     — nuovo
    cute_list.py       — (ex widgets.py)

  ... (editor_toolbar, file_tree_panel, search_panel, toc_panel, etc. — invariati)
```

---

## Ordine di Esecuzione

L'ordine è progettato per minimizzare i conflitti e permettere commit atomici:

| Step | Fase | Descrizione | Rischio |
|---|---|---|---|
| 1 | 1.1 | Creare `core/constants.py` | Basso |
| 2 | 1.2 | Aggiornare riferimenti alle costanti | Medio (tanti file) |
| 3 | 1.3 | Centralizzare shortcut categories | Basso |
| 4 | 1.4 | Centralizzare path resolution | Basso |
| 5 | 2 | Consolidare `core/services/` | Basso |
| 6 | 3.1 | Estrarre `ActionRegistry` | Medio |
| 7 | 3.2 | Estrarre `SidePanelManager` | Medio |
| 8 | 3.3 | Estrarre `WindowStateManager` | Basso |
| 9 | 3.4 | Estrarre `SettingsApplicator` | Medio |
| 10 | 4.1 | Estrarre `LineNumberArea` | Basso |
| 11 | 4.2 | Estrarre `PreviewManager` + anchor in thread | Alto |
| 12 | 4.3 | Estrarre `LinkManager` + debounce | Alto |
| 13 | 4.4 | Estrarre `DropHandler` | Basso |
| 14 | 5 | Snellire `settings_dialog.py` | Alto |
| 15 | 6 | Consolidare i dati tema | Medio |
| 16 | 7 | Ottimizzazioni performance | Basso (incrementali) |
| 17 | 8 | Normalizzazioni minori | Basso |
| 18 | 9 | Riorganizzare struttura package | Basso (rinomine) |

---

## Riepilogo dei Benefici Attesi

| Beneficio | Dettaglio |
|---|---|
| **Manutenibilità** | `MainWindow` da 2179 → 800 linee; `EditorTab` da 1520 → 600 linee; `SettingsDialog` da 838 → 200 linee |
| **Riusabilità** | Widget estratti (`ToggleSwitch`, `FontPicker`) riusabili in altri progetti |
| **Performance** | `build_file_index` cachato, `build_line_anchor_map` in worker thread, `_gnome_animations_enabled` cachato, icon cache, broken-link debounce separato |
| **Consistenza** | Unica fonte di verità per costanti, path resolution, logging |
| **Testabilità** | Componenti più piccoli e isolati possono essere testati più facilmente in futuro |
| **Zero regressioni** | La logica di business non viene toccata — solo refactoring strutturale |
