# CuteMD v1.1.0 — Second Performance & Quality Pass

> Branch `refactor/performance-pass` — June 2026

---

## 1. Executive Summary

Dopo il refactoring architetturale (v1.1.0) la codebase è molto più sana: -22% su
`main_window.py`, -27% su `editor_tab.py`, 14 moduli estratti, 0 duplicazioni.
Questo secondo passaggio si concentra su **performance** e **fluidità**:
operazioni bloccanti sul main thread, computazioni che possono essere rese
asincrone o lazy, e pattern inefficienti residui.

---

## 2. Problemi Identificati

### 2.1 `link_preview_popup.py` — 680 linee, rendering sincrono

| Riga | Metodo | Problema |
|---|---|---|
| ~326 | `_show_pdf()` | `doc.render(0, QSize(w, h))` è sincrono sul main thread. Su PDF grandi il popup lagga |
| ~342 | `_show_csv()` | `csv.reader` + `list(reader)[:100]` sincrono. File CSV grandi bloccano |
| ~380 | `_show_text()` | `path.read_text()` sincrono per file di testo. Su file >1MB blocca |
| ~430 | `_show_cbz_page()` | `zf.read(name)` + `QPixmap.loadFromData()` sincrono. Immagini CBZ grandi bloccano |

**Fix**: Spostare TUTTI i `_show_*` in un QThread (come già fatto per XLSX/DOCX/PPTX/EPUB).

### 2.2 `markdown/document_renderers.py` — xlsx_to_html su main thread

| Riga | Problema |
|---|---|
| ~42 | `openpyxl.load_workbook(str(path), read_only=True, data_only=True)` — chiamato **sincrono** quando l'anteprima principale carica un `.xlsx`. Blocca l'intera UI |

**Fix**: Spostare `xlsx_to_html`, `docx_to_html`, `pptx_to_html` in QThread anche per
il rendering dell'anteprima principale (non solo il popup hover).

### 2.3 `editor_tab.py` — Doppio calcolo anchor map

| Riga | Problema |
|---|---|
| ~700-710 | `_update_preview()` calcola `self._last_anchor` usando `_line_anchor_map` |
| ~783-790 | `_on_preview_ready()` ricalcola `_line_anchor_map` da zero con `build_line_anchor_map()` |

L'anchor map viene calcolata due volte: una (stale) in `_update_preview` per il
`_last_anchor`, e una (fresh) in `_on_preview_ready`. Si può calcolare una volta
sola.

**Fix**: Calcolare `_line_anchor_map` in `_on_preview_ready` e usarla direttamente,
saltando il calcolo in `_update_preview` quando la mappa è già disponibile.

### 2.4 `editor_tab.py` — `_load_document()` render sincrono

| Riga | Problema |
|---|---|
| ~470 | `_load_document()` chiama `xlsx_to_html()`, `docx_to_html()`, `pptx_to_html()` sul main thread quando si apre un file Office/CBZ/EPUB |

**Fix**: Spostare in QThread come fatto per il popup hover.

### 2.5 `main_window.py` — `_apply_theme()` ridondante

`_apply_theme()` chiama `_recolor_toolbar_icons()` che itera su tutti i bottoni
anche se il colore non è cambiato (la cache delle icone mitiga ma non elimina
l'iterazione).

### 2.6 `main_window.py` — `_check_for_updates()` su main thread

`check_for_update()` fa una richiesta HTTP sincrona (`requests.get`). Anche se
chiamata con `QTimer.singleShot(4000, ...)`, blocca il main thread per la durata
della richiesta.

### 2.7 `syntax_highlighter.py` — Regex su file grandi

Il meccanismo di skip per file >4000 linee funziona ma è binario (o tutto o niente).
Si potrebbe fare un approccio graduale: ridurre progressivamente i pattern
applicati all'aumentare delle linee.

### 2.8 `search_panel.py` — `_replace_all_in_files()` I/O sincrono

Legge e scrive file uno per uno sul main thread. Su molteplici file grandi,
l'UI si blocca.

### 2.9 `find_bar.py` — `_replace_all()` blocca undo stack

`cursor.beginEditBlock()` / `cursor.endEditBlock()` raggruppa tutte le modifiche
in un unico undo step — corretto. Ma l'iterazione su tutte le occorrenze è
sincrona e blocca il repaint.

### 2.10 `file_tree_panel.py` — `QFileSystemModel.setRootPath()` sincrono

Su directory con migliaia di file, `setRootPath()` blocca l'UI per secondi durante
la scansione iniziale.

### 2.11 `settings_dialog.py` — Inizializzazione eager di tutte le pagine

Il `__init__` costruisce TUTTE e 7 le pagine del dialog immediatamente, anche se
l'utente ne visita solo 1-2. La costruzione include `QFontDatabase().families()`
(delegata a thread, ok) e la creazione di centinaia di widget.

### 2.12 `core/webdav/sync.py` — `sync_folder()` mostruoso (230 linee)

Il metodo fa tutto: connessione, listing remoto, scansione locale, confronto,
upload/download. È corretto che giri in un QThread, ma è difficile da testare
e mantenere.

### 2.13 `ui/markdown_completer.py` — Regex module-level ma complesse

Le regex `_RE_UNORDERED`, `_RE_ORDERED`, `_RE_TASK`, `_RE_BLOCKQUOTE` sono
pre-compilate (bene). Il metodo `_continue_list()` fa matching su ogni Enter
— ok, è il suo scopo.

### 2.14 `ui/link_manager.py` — `refresh_broken_links()` chiamato ad ogni textChanged

Anche se debounced dal timer della preview, viene comunque chiamato frequentemente.
Per ogni match regex, chiama `_resolve_link_target(quick=True)` che fa
`resolve_link_target` con `quick=False` implicito... no, con `quick=True`.

**Fix**: Aggiungere un debounce separato per broken links (500ms).

---

## 3. Riepilogo Priorità

| # | Problema | Impatto | Difficoltà |
|---|---|---|---|
| 2.1 | Link preview popup: rendering PDF/CSV/CBZ sincrono | Medio | Media |
| 2.2 | Document renderer xlsx/docx/pptx sincrono in anteprima principale | Alto | Media |
| 2.4 | `_load_document` sincrono | Alto | Media |
| 2.8 | `_replace_all_in_files` I/O sincrono | Medio | Bassa |
| 2.10 | `QFileSystemModel.setRootPath` bloccante | Medio | Alta |
| 2.3 | Doppio calcolo anchor map | Basso | Bassa |
| 2.7 | Syntax highlighter graduale | Basso | Bassa |
| 2.12 | `sync_folder` refactoring | Basso | Alta |
| 2.14 | Broken link debounce separato | Basso | Bassa |
| 2.6 | Update check HTTP su main thread | Basso | Bassa |
| 2.11 | Settings dialog lazy pages | Medio | Media |

---

*Analisi completata il 27 Giugno 2026*
