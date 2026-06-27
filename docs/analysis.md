# CuteMD — Architectural Analysis

> Branch `refactor/normalize-architecture` — June 2026

---

## 1. Executive Summary

CuteMD è un editor Markdown non-WYSIWYG costruito su PySide6, con supporto a WebDAV sync, aggiornamenti automatici, temi multipli, e anteprima live. L'applicazione funziona e ha feature avanzate, ma la codebase ha accumulato debito tecnico significativo in termini di separazione delle responsabilità, duplicazione, e complessità ciclomatica.

L'analisi copre **45 file Python** (esclusi `.venv` e `__pycache__`) per un totale stimato di ~15,000 linee di codice.

---

## 2. Panoramica dei Package

| Package | Files | Qt imports? | Responsabilità dichiarata |
|---|---|---|---|
| `core/` | 8 (+ `services/` 5, `webdav/` 2) | ❌ No | Logica pura, utility, aggiornamenti |
| `markdown/` | 5 | ❌ No | Rendering Markdown → HTML, Pygments |
| `ui/` | 27 | ✅ Sì | GUI completa (finestre, widget, dialog) |
| `main.py` | 1 | ✅ Sì | Entry point |

---

## 3. Problemi Identificati — Dettaglio

### 3.1 `main_window.py` — **God Object** (2179 lines)

Questo è il problema più grave. `MainWindow` gestisce praticamente **tutto**:

- Setup azioni e menubar (~150 lines)
- Setup central widget con sidebar, toolbar, splitter, tab, status bar (~250 lines)
- Gestione animazioni splitter (~80 lines)
- Gestione pannelli laterali (tree/search/TOC) (~120 lines)
- Gestione tab (add, close, change, modified, title, save) (~80 lines)
- Gestione toolbar e icone colorate (~60 lines)
- Gestione file (open/save/save_as/new/close folder) (~200 lines)
- Gestione link click / creazione file mancanti (~40 lines)
- Gestione autosave, auto-sync (~60 lines)
- Gestione session save/restore (~60 lines)
- Gestione settings dialog e applicazione modifiche (~200 lines)
- Gestione zoom editor/preview (~50 lines)
- Gestione WebDAV sync (~80 lines)
- Gestione update check (~60 lines)
- Gestione command palette, shortcuts dialog (~40 lines)
- Gestione retranslate e changeEvent (~60 lines)
- Gestione window title e stato (~50 lines)
- Gestione tree file operations (rename, delete, drag-drop reactions) (~60 lines)
- Gestione tabelle e azioni duplicate (in tre posti: menubar, command palette, shortcuts dialog)

**Impatto sulla performance**: Nessun problema diretto, ma la manutenibilità è critica — ogni modifica a una feature richiede di navigare 2179 linee.

### 3.2 `editor_tab.py` — **Secondo God Object** (1520 lines)

`EditorTab` è un singolo widget che:

- Contiene editor + preview + stack + find bar + splitter
- Gestisce line number area (classe annidata `LineNumberArea`)
- Gestisce file I/O (load, save, save_as, auto_save, maybe_save)
- Gestisce rendering preview (async via thread, con debounce e hash tracking)
- Gestisce scroll sync bidirezionale editor↔preview
- Gestisce link detection, hover underline, click navigation, broken link highlighting
- Gestisce link preview popup (timer, cursor tracking, popup show/hide)
- Gestisce drag & drop di file
- Gestisce paste di immagini da clipboard
- Gestisce zoom editor e preview
- Gestisce find bar integration
- Gestisce caricamento immagini, PDF, documenti Office, CBZ, EPUB
- Gestisce smart editing (via `MarkdownAutoCompleter`)
- Gestisce syntax highlighting (via `MarkdownHighlighter`)
- Gestisce highlight della linea corrente

**Impatto sulla performance**: Ogni `textChanged` triggera il debounce preview e la risoluzione dei broken link. Su file > 2000 linee, la risoluzione link viene skippata ma il debounce preview rimane. Il rendering preview avviene in un thread separato (OK), ma il build dell'`anchor_map` avviene sul main thread a ogni textChanged.

### 3.3 `settings_dialog.py` — **Terzo God Object** (838 lines)

Contiene al suo interno:

- `_FontPreviewDelegate`
- `_ToggleSwitch` (widget custom)
- `_FontPicker` (widget custom con logica di filtro)
- `_WebDAVTestWorker` (QThread)
- `SettingsDialog` (classe principale con 7 pagine di settings)

Questi widget interni dovrebbero essere estratti in moduli separati.

### 3.4 Duplicazione di Dati e Responsabilità

#### 3.4.1 Estensioni file duplicate
Le estensioni `_IMG_EXTS`, `_PDF_EXTS`, `_MD_EXTS`, `_DOC_EXTS` sono definite in **almeno 3 posti diversi**:

| File | Definisce |
|---|---|
| `core/services/link_resolver.py` | `_IMG_EXTS`, `_PDF_EXTS` |
| `ui/editor_tab.py` | `_MD_EXTS`, `_IMG_EXTS`, `_PDF_EXTS`, `_DOC_EXTS` |
| `ui/link_preview_popup.py` | `_MD_EXTS`, `_IMG_EXTS`, `_PDF_EXTS`, più CSV/CBZ/EPUB/DOCX/PPTX/XLSX |
| `markdown/image_utils.py` | `_IMG_EXTS_RE` (regex) |
| `markdown/document_renderers.py` | `_IMG_EXTS` in `cbz_to_html` |

#### 3.4.2 Azioni duplicate
La mappa delle azioni (`_all_actions` dict + azioni per command palette + azioni per shortcuts dialog) è ripetuta **tre volte** con piccole variazioni in `main_window.py`.

#### 3.4.3 Categorie shortcuts duplicate
`_SHORTCUT_CATEGORIES` è definito in `shortcuts_dialog.py` e ripetuto (con `_CAT_ORDER`) in `command_palette.py`.

#### 3.4.4 Risoluzione dei path (PyInstaller-aware) duplicata
Ogni modulo UI ha la propria copia del pattern `getattr(sys, "frozen", False)` per risolvere i path. Dovrebbe essere centralizzato.

### 3.5 Accoppiamento `ui/` ↔ `markdown/`

Il vincolo è documentato (il package `markdown/` non può importare da `ui/`), ma ci sono import circolari indiretti:

- `markdown/html_builder.py` importa da `markdown/image_utils.py` → `SizeProvider` (un `Callable`)
- `ui/preview_worker.py` importa `markdown/html_builder.py:build_html`
- `ui/preview_browser.py` importa `markdown/image_utils.py` e fornisce `get_image_size`
- `ui/editor_tab.py` importa `markdown/document_renderers.py` per Office/CBZ/EPUB

Questo è sostanzialmente OK, ma il `SizeProvider` callback è un pattern fragile.

### 3.6 Overlap `core/theme_data.py` ↔ `ui/themes.py`

C'è una duplicazione quasi completa tra:

- `core/theme_data.py`: `ThemeData` dataclass (16 campi colore come stringhe hex) + `ALL_THEMES_DATA`
- `ui/themes.py`: `Theme` dataclass (16 campi colore come `QColor`) + `ALL_THEMES` + `system_theme()`

`core/theme_data.py` esiste perché "non deve importare Qt", ma di fatto è un doppione. La conversione da `ThemeData` a `Theme` avviene in `_theme_from_data()` in `ui/themes.py`. Questo layer aggiuntivo è puro overhead senza reale beneficio.

### 3.7 `core/services/` — Troppi Mini-File

| File | Righe | Responsabilità |
|---|---|---|
| `anchor_map.py` | 53 | Una funzione `build_line_anchor_map` |
| `file_io.py` | 21 | Una funzione `read_file_with_encoding` |
| `folder_setup.py` | 15 | Una funzione `default_folder_config` |
| `link_resolver.py` | 113 | Una funzione `resolve_link_target` |
| `recent_folders.py` | 12 | Una funzione `update_recent_folders` |

Questi file da 1-funzione causano eccessiva frammentazione senza reale beneficio di separazione. Potrebbero essere consolidati in 1-2 moduli più coesi (`core/file_utils.py`, `core/link_utils.py`).

### 3.8 Logging non uniforme

- `core/logging.py` usa `logging.getLogger` + `StreamHandler(sys.stderr)`
- `ui/preview_browser.py` usa `logging.getLogger` **senza** passare da `setup_logging`
- Tutti gli altri moduli usano `core.logging.setup_logging`

### 3.9 Gestione Memoization / Cache Inefficiente

`editor_tab.py` ha molteplici meccanismi di cache:

- `_cached_text` / `_cached_text_hash` — invalidato a ogni textChanged
- `_link_resolve_cache` — dizionario pulito a ogni textChanged
- `_last_rendered_hash`, `_pending_render_hash` — per skip di render identici
- `_line_anchor_map_hash` — per skip del rebuild anchor map
- `_preview_busy` / `_preview_pending` — per gestione render asincroni

Questi flag sono sparsi in 6+ attributi e interagiscono in modi sottili. La logica andrebbe incapsulata in un oggetto dedicato.

### 3.10 `file_tree_panel.py` — Classi Annidate con Logica Mista

Contiene tre classi:
- `_FileTreeView(QTreeView)` — custom tree con drag-drop e keyboard shortcuts
- `_DotFileFilterProxy(QSortFilterProxyModel)` — filtro per hidden files
- `FileTreePanel(QWidget)` — container con segnali e operazioni file (rename, delete, move, duplicate)

`FileTreePanel._move_items()` contiene logica di I/O file complessa (overwrite prompt, shutil.move, shutil.rmtree) — dovrebbe delegare a `core/`.

### 3.11 `search_panel.py` — Ricerca con Chunked Timer

Il pattern di ricerca chunked (processa 20 file ogni 10ms) è valido per evitare di bloccare l'UI, ma:
- Non c'è supporto per regex (usa `re.escape` sempre)
- La replace singola modifica solo la linea esatta, non gestisce modifiche concorrenti
- `_replace_all_in_files` legge e scrive tutti i file uno per uno — potrebbe essere batch-ottimizzato

### 3.12 `link_preview_popup.py` — Feature Creep

Questo file (500+ lines) gestisce l'anteprima hover per **tutti** i tipi di file:
- Testo/Markdown con syntax highlighting
- Immagini (QPixmap scaling)
- PDF (QPdfDocument rendering)
- CSV/TSV (parsing e formattazione)
- CBZ (navigazione pagina)
- PPTX (navigazione slide)
- EPUB, DOCX, XLSX

La logica di preview per DOCX/PPTX/XLSX/EPUB **duplica** quella in `editor_tab.py` e `document_renderers.py`.

### 3.13 `image_utils.py` — Duplicazione della Risoluzione Path

La risoluzione dei path immagine in `markdown/image_utils.py` (con `build_file_index` e `resolve_image_path`) duplica parzialmente la logica di `core/services/link_resolver.py:resolve_link_target`. Due sistemi di risoluzione indipendenti che fanno cose simili con regole simili.

### 3.14 `syntax_highlighter.py` — Warning di Performance

`MarkdownHighlighter.highlightBlock()` applica 9 regex diverse su **ogni linea** del documento a ogni rehighlight. Su file molto grandi (>5000 linee) questo può causare lag durante lo scrolling.

Mancano ottimizzazioni come:
- Limitare l'highlight alle sole linee visibili
- Compilare le regex una volta sola (già fatto con attributi di classe, OK)
- Evitare rehighlight completi quando si modifica una sola linea

### 3.15 `animation_speed.py` — Init costoso

`_gnome_animations_enabled()` esegue un `subprocess.run(["gsettings", ...])` — questo viene chiamato a **ogni** animazione. Su GNOME, è un fork + exec ogni volta che si apre/chiude un pannello. Dovrebbe essere cachato.

### 3.16 `core/desktop_integration.py` — Naming e Organizzazione

`_resolve_path_in_bundle()` in `desktop_integration.py` è una terza copia del pattern di risoluzione path PyInstaller-aware. Inoltre, questo modulo è usato solo per integrazione desktop Linux — non dovrebbe stare in `core/`.

---

## 4. Problemi di Performance

### 4.1 `_refresh_link_highlights()` su ogni textChanged

Ad ogni modifica del testo, `editor_tab.py` chiama `_refresh_link_highlights()` che applica **due** regex sull'intero documento e per ogni match chiama `_resolve_link_target(target, quick=True)`. Questo scala quadraticamente con la dimensione del documento.

**Quick fix**: Debounce separato per i broken link highlights (es. 500ms dopo l'ultimo textChanged).

### 4.2 `build_html()` chiama `build_file_index()` ad ogni render

`markdown/html_builder.py:build_html()` chiama `build_file_index(vault_root)` che fa un `rglob("*")` sull'intero vault ad **ogni** render della preview. Su vault con migliaia di file, questo è molto costoso.

**Fix**: Il file index dovrebbe essere cachato e invalidato solo quando la struttura del vault cambia.

### 4.3 `_apply_theme()` ricrea tutte le icone SVG

`MainWindow._apply_theme()` → `_recolor_toolbar_icons()` → per ogni bottone, rilegge il file SVG, lo renderizza in un QPixmap, lo ricolora, e lo trasforma in QIcon. Questo avviene ad ogni cambio tema.

**Fix**: Cache dei QIcon colorati per colore.

### 4.4 `build_line_anchor_map()` su main thread

Chiamato sincronicamente ad ogni textChanged (nel debounce del preview timer). Parsing dell'intero documento con markdown-it. Su file > 10KB contribuisce al lag di typing.

**Fix**: Anch'esso potrebbe essere spostato nel worker thread.

---

## 5. Riepilogo Quantitativo

| Metrica | Valore |
|---|---|
| File Python totali | 45 |
| Linee stimate | ~15,000 |
| Classi con >500 linee | 4 (`MainWindow`, `EditorTab`, `SettingsDialog`, `LinkPreviewPopup`) |
| Funzioni standalone in file da soli | 5 |
| Definizioni duplicate (estensioni file) | 4+ |
| Definizioni duplicate (azioni QAction) | 3 |
| Definizioni duplicate (path resolution) | 3 |
| Package con Qt import nonostante la regola | 0 (la regola è rispettata) |
| Import logging non uniforme | 1 (`preview_browser.py`) |
| Pattern di cache/flag sparsi | `editor_tab.py` ha 8+ flag di stato rendering |

---

## 6. Diagramma delle Dipendenze

```
main.py
  ├── core/logging.py
  ├── ui/main_window.py ◀── 2179 lines, God Object
  │     ├── core/animation_speed.py
  │     ├── core/folder_settings.py
  │     ├── core/services/folder_setup.py
  │     ├── core/services/link_resolver.py
  │     ├── core/services/recent_folders.py
  │     ├── core/webdav/sync.py
  │     ├── ui/theme.py + ui/themes.py + ui/theme_manager.py
  │     ├── ui/editor_tab.py ◀── 1520 lines, Secondo God Object
  │     │     ├── core/animation_speed.py
  │     │     ├── core/services/anchor_map.py
  │     │     ├── core/services/file_io.py
  │     │     ├── core/services/link_resolver.py
  │     │     ├── markdown/html_builder.py
  │     │     ├── markdown/document_renderers.py
  │     │     ├── markdown/image_utils.py
  │     │     ├── ui/find_bar.py
  │     │     ├── ui/image_viewer.py
  │     │     ├── ui/pdf_viewer.py
  │     │     ├── ui/preview_browser.py
  │     │     ├── ui/preview_worker.py
  │     │     ├── ui/syntax_highlighter.py
  │     │     ├── ui/markdown_completer.py
  │     │     └── ui/link_preview_popup.py
  │     ├── ui/editor_toolbar.py
  │     ├── ui/editor_context_menu.py
  │     ├── ui/file_tree_panel.py
  │     ├── ui/search_panel.py
  │     ├── ui/toc_panel.py
  │     ├── ui/settings_dialog.py ◀── 838 lines
  │     ├── ui/command_palette.py
  │     ├── ui/shortcuts_dialog.py
  │     ├── ui/welcome_dialog.py
  │     ├── ui/update_dialog.py
  │     ├── ui/webdav_sync.py
  │     └── ui/widgets.py
  └── ui/translations.py
```

---

*Analisi completata il 27 Giugno 2026*
