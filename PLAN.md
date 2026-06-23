# CuteMD — Refactoring Plan

## Diagnosi dello stato attuale

| File | Righe | Problema |
|---|---|---|
| `ui/main_window.py` | 1621 | **God class**: 50+ metodi — costruisce UI, gestisce file, sync, impostazioni, temi, font, search, toolbar, menu, link navigation, recent folders |
| `ui/editor_tab.py` | 829 | Troppe responsabilità: editing, preview rendering, scroll sync, find bar, link nav, caricamento immagini/PDF |
| `ui/settings_dialog.py` | 614 | `__init__` di ~300 righe costruisce 6 pagine inline |
| `ui/webdav_sync.py` | 400 | `sync_folder` di ~155 righe con albero decisionale complesso |
| `markdown/html_builder.py` | 84 | Viola il confine `markdown/` importando da `ui.preview_browser` |
| `ui/preview_browser.py` | 139 | Contiene funzioni di manipolazione stringhe che dovrebbero stare in `markdown/` |

### Problemi trasversali

- **`QSettings` istanziato in 8+ punti** tra 5 file — nessuna fonte centralizzata
- **Cambio tema/font propagato manualmente** iterando tutte le tab — nessun event system
- **Stringhe di sintassi Markdown duplicate** in 3 punti: toolbar, context menu, `_insert_md`
- **Logica checkbox zoom PDF duplicata** 3 volte identica in `pdf_viewer.py`
- **`_SyncThread` definita inline** dentro un metodo di `MainWindow` — rompe l'incapsulamento
- **Accesso diretto a stato privato:** `EditorTab._file_path` da `main_window.py`, `PdfViewer._scroll` da `editor_tab.py`
- **Colori syntax highlighter hardcodati** anziché derivati dal tema corrente
- **`_EXCLUDE_DIRS` hardcodato** nel sync engine

---

## Piano di refactoring

### Fase 1 — Separare il confine `markdown/` ↔ `ui/`

**Obiettivo:** Il package `markdown/` non deve importare da `ui/`, come da specifica in `AGENTS.md`.

#### 1.1 Nuovo file `markdown/image_utils.py`
Spostare `add_img_dimensions()` e `fix_image_paragraphs()` da `ui/preview_browser.py`.
Sono funzioni pure di manipolazione stringhe. La lookup delle dimensioni immagine va resa un parametro (callback `size_lookup: Callable[[str], tuple[int, int] | None]`) così `markdown/` non importa `QImage`.

#### 1.2 Correggere `markdown/html_builder.py`
Rimuovere l'import `from ui.preview_browser import ...` e usare invece `markdown/image_utils.py`.

#### 1.3 Adattare `ui/preview_browser.py`
Usare le funzioni da `markdown/image_utils.py` passando la callback `QImage` come `size_lookup`. Il file si riduce da 139 a ~90 righe.

---

### Fase 2 — Estrarre toolbar e azioni Markdown

**Obiettivo:** Rimuovere ~200 righe da `MainWindow` ed eliminare la duplicazione delle sintassi.

#### 2.1 Nuovo file `ui/markdown_actions.py`
Registro centralizzato delle azioni di formattazione Markdown.

```python
@dataclass
class MarkdownAction:
    action_id: str
    label: str
    icon: str          # nome SVG
    syntax: str        # e.g. "**" per bold
    tooltip: str

ACTIONS: dict[str, MarkdownAction]
```

Usato sia dalla toolbar che dal context menu editor per garantire che le sintassi rimangano sincronizzate.

#### 2.2 Nuovo file `ui/editor_toolbar.py` — classe `EditorToolbar(QWidget)`
Costruzione della toolbar dell'editor (attualmente `_make_editor_toolbar()` in `main_window.py`). Gestisce:
- Bottoni di formattazione (letti da `markdown_actions.ACTIONS`)
- Menu heading a discesa
- Icone colorate via `QSvgRenderer`
- Connessione azioni all'editor corrente

#### 2.3 Nuovo file `ui/editor_context_menu.py` — classe `EditorContextMenu(QMenu)`
Costruzione del menu contestuale dell'editor (attualmente `_on_editor_context_menu()` in `main_window.py`). Legge anch'esso da `markdown_actions.ACTIONS`.

---

### Fase 3 — Estrarre sync e search

**Obiettivo:** Altri ~300 righe fuori dalla God class.

#### 3.1 Spostare `_SyncThread` in `ui/webdav_sync.py`
La classe `_SyncThread(QThread)` è attualmente definita inline dentro `_on_webdav_sync()` a righe 1088-1108 di `main_window.py`. Va spostata in `webdav_sync.py`, rinominata `SyncThread`, con segnali espliciti (`sync_progress`, `sync_finished`, `sync_error`) così che `MainWindow` si limiti a connetterli.

#### 3.2 Nuovo file `ui/search_panel.py` — classe `SearchPanel(QWidget)`
Il pannello di ricerca nei file (attualmente costruito in `MainWindow._make_search_panel()`). Incapsula:
- Campo query + checkbox case-sensitive
- Lista risultati
- Slot di navigazione (Enter, doppio click)
- Segnale `file_activated(str)` per aprire il file selezionato

---

### Fase 4 — Centralizzare impostazioni, tema, font

**Obiettivo:** Eliminare la dispersione di `QSettings` e la propagazione manuale di tema/font.

#### 4.1 Nuovo file `ui/settings_manager.py` — classe `SettingsManager`
Singleton che wrappa `QSettings("cutemd", "cutemd")`. Metodi tipizzati per ogni chiave:

```python
class SettingsManager(QObject):
    font_changed = Signal()
    theme_changed = Signal()
    language_changed = Signal()

    def editor_font_family(self) -> str: ...
    def set_editor_font_family(self, value: str) -> None: ...
    # ... tutte le chiavi QSettings e folder_settings
```

`MainWindow` smette di chiamare `QSettings.value()` / `setValue()` direttamente. I widget interessati si connettono ai segnali di `SettingsManager` e si aggiornano da soli.

#### 4.2 Nuovo file `ui/theme_manager.py` — classe `ThemeManager`
```python
class ThemeManager(QObject):
    current_theme_changed = Signal(Theme)

    def current_theme(self) -> Theme: ...
    def set_theme(self, name: str) -> None: ...
    def apply_to(self, widget: QWidget) -> None: ...
```
`EditorTab.set_theme()`, `syntax_highlighter.set_theme()`, e la toolbar si connettono a `current_theme_changed` anziché essere chiamati manualmente da `MainWindow._apply_theme()`.

#### 4.3 Eliminare `"Sistema"` backward compat duplicato
Le righe 78-79 e 83-84 di `main_window.py` (mapping `"Sistema"` → `"System"`) vanno unificate in `SettingsManager`.

---

### Fase 5 — Snellire `editor_tab.py`

**Obiettivo:** Da 829 a ~400 righe.

#### 5.1 Nuovo file `ui/scroll_sync.py` — classe `ScrollSynchronizer`
Estrarre da `EditorTab`:
- `_last_anchor`, `_line_anchor_map`, `_line_anchor_map_hash`, `_pending_sync_anchor`, `_sync_retries` (6 variabili di stato)
- `_build_line_anchor_map()`
- `_scroll_editor_to_anchor()` e `_scroll_preview_to_line()`
- La logica di `_on_editor_scroll_changed()` e `_on_preview_anchor_clicked()`

`ScrollSynchronizer` riceve l'editor e la preview come parametri.

#### 5.2 Nuovo file `ui/find_bar.py` — classe `FindBar(QWidget)`
Widget autonomo per search/replace:
- Campo testo + checkbox case-sensitive
- Pulsanti Next/Prev/Replace/Replace All
- Highlight delle occorrenze
- Segnali: `find_next`, `find_prev`, `replace`, `replace_all`
- Scorciatoie: Enter/F3, Shift+F3, Esc per chiudere

#### 5.3 Correggere accesso a `PdfViewer._scroll` (riga 214)
Aggiungere un metodo pubblico `PdfViewer.scroll_widget()` o usare un segnale per la scroll sync su PDF.

---

### Fase 6 — Pulizie mirate

**Obiettivo:** Eliminare duplicazioni residue e accorciare metodi lunghi.

#### 6.1 `ui/pdf_viewer.py` — estrarre `_uncheck_fit_modes()`
Blocco duplicato 3 volte (zoom_in, zoom_out, eventFilter Ctrl+scroll):
```python
def _uncheck_fit_modes(self):
    self._fit_width = False
    self._fit_height = False
    self._fit_width_cb.blockSignals(True)
    self._fit_width_cb.setChecked(False)
    self._fit_width_cb.blockSignals(False)
    self._fit_height_cb.blockSignals(True)
    self._fit_height_cb.setChecked(False)
    self._fit_height_cb.blockSignals(False)
```

#### 6.2 `markdown/math_renderers.py` — estrarre `_escape_html()`
```
_escape_html(content) → content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```
Duplicato in tutti e 4 i renderer (svg2mathml, mml2mathml, latex2mathml, math2text).

#### 6.3 `ui/settings_dialog.py` — spezzare `__init__`
Ogni pagina (language, theme, editor, preview, storage, shortcuts, sync) diventa un metodo privato `_build_*_page(parent)` da max ~40 righe. `__init__` si riduce a ~50 righe di setup + chiamate ai metodi.

#### 6.4 `ui/webdav_sync.py` — spezzare `sync_folder()`
Estrarre:
- `_scan_local(dir:)` — elenca file locali
- `_load_state(dir:)` — carica `sync_state.json`
- `_decide_actions(local, remote, state)` — albero decisionale (8 branch)
- `_execute_actions(actions, client, dir)` — upload/download/delete

#### 6.5 `ui/welcome_dialog.py` + `main_window.py` — unificare recent folders
Estrarre logica duplicata di parsing `"recent_folders"` in `settings_manager.py`.

#### 6.6 `ui/syntax_highlighter.py` — colori da tema
Usare i colori della palette Qt invece dei colori hardcodati per dark/light (righe 72-95). Si connette a `theme_manager.current_theme_changed`.

---

## Riepilogo nuovi file

```
ui/
├── markdown_actions.py        # Registro azioni formattazione
├── editor_toolbar.py          # Toolbar editor (estratta da MainWindow)
├── editor_context_menu.py     # Menu contestuale editor (estratto da MainWindow)
├── search_panel.py            # Pannello ricerca nei file (estratto da MainWindow)
├── settings_manager.py        # Singleton QSettings tipizzato
├── theme_manager.py           # Propagazione tema via segnali
├── scroll_sync.py             # ScrollSync (estratto da EditorTab)
├── find_bar.py                # Find bar (estratto da EditorTab)

markdown/
├── image_utils.py             # add_img_dimensions, fix_image_paragraphs (da preview_browser)
```

## Riduzione attesa per file

| File | Prima (righe) | Dopo (righe) |
|---|---|---|
| `main_window.py` | 1621 | ~800 |
| `editor_tab.py` | 829 | ~400 |
| `settings_dialog.py` | 614 | ~450 |
| `webdav_sync.py` | 400 | ~350 |
| `preview_browser.py` | 139 | ~90 |
| `pdf_viewer.py` | 249 | ~220 |
| `math_renderers.py` | 57 | ~45 |
| **Nuovi file totali** | 0 | ~600 |

Totale lordo invariato (~4850 righe), ma distribuito su più moduli piccoli e monoresponsabilità.
