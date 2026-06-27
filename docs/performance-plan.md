# CuteMD v1.1.0 — Performance Improvement Plan

> Branch `refactor/performance-pass` — June 2026

---

## Phase A — Async Rendering for Main Preview (PRIORITY: HIGH)

**Problema**: `editor_tab._load_document()` e `document_renderers.py` chiamano
`openpyxl`, `python-docx`, `python-pptx` sul **main thread**, bloccando l'UI
quando si apre un file `.xlsx`/`.docx`/`.pptx` nell'anteprima principale.

**Fix**: Spostare il rendering in un QThread, mostrando "Rendering..." nella
preview mentre carica.

### A.1 — Creare `markdown/async_renderer.py`

```python
class AsyncDocRenderer(QThread):
    """Renders XLSX/DOCX/PPTX/CBZ/EPUB in background thread."""
    result = Signal(str)

    def __init__(self, path: Path, css: str):
        self._path = path
        self._css = css

    def run(self):
        ext = self._path.suffix.lower()
        if ext == ".xlsx":
            html = xlsx_to_html(self._path, self._css)
        elif ext == ".docx":
            html = docx_to_html(self._path, self._css)
        elif ext == ".pptx":
            html = pptx_to_html(self._path, self._css)
        elif ext == ".cbz":
            html = cbz_to_html(self._path, self._css)
        elif ext == ".epub":
            html = epub_to_html(self._path, self._css)
        self.result.emit(html)
```

### A.2 — Modificare `editor_tab._load_document()`

- Avviare `AsyncDocRenderer` in un thread
- Mostrare immediatamente "Rendering..." nella preview
- Al segnale `result`, chiamare `self.preview.setHtml(html)`

---

## Phase B — Async Link Preview per Tutti i Formati (PRIORITY: HIGH)

**Problema**: `link_preview_popup.py` renderizza PDF, CSV, CBZ, immagini grandi
sul main thread. Solo XLSX/DOCX/PPTX/EPUB sono già async.

**Fix**: Estendere il `_PreviewRenderThread` a TUTTI i formati, mostrando il
popup con un placeholder "Loading..." universale.

### B.1 — Unificare `_PreviewRenderThread`

```python
class _PreviewRenderThread(QThread):
    result_html = Signal(str)
    result_image = Signal(QPixmap)
    result_text = Signal(str)

    def __init__(self, path: Path, ext: str, css: str, max_w: int, max_h: int):
        # dispatch to correct renderer
```

### B.2 — Modificare `show_for_path()`

- Tutti i formati passano attraverso il thread
- Il popup appare immediatamente con "Loading..."
- Al segnale, aggiorna il contenuto

---

## Phase C — Search Panel Async I/O (PRIORITY: MEDIUM)

**Problema**: `search_panel._replace_all_in_files()` legge e scrive file sul main
thread.

### C.1 — QThread per replace massiva

```python
class _ReplaceThread(QThread):
    progress = Signal(int, int)  # current, total
    done = Signal(int, int)  # replaced_count, files_modified

    def __init__(self, files: dict[Path, list[int]], query: str, replacement: str, flags: int):
        ...
```

---

## Phase D — Quick Wins (PRIORITY: LOW)

### D.1 — Doppio calcolo anchor map

In `editor_tab._update_preview`, se `_line_anchor_map` è già disponibile (non vuota),
usarla senza ricalcolare `_last_anchor` in `_on_preview_ready`.

### D.2 — Debounce broken-link highlights

Aggiungere un `QTimer` separato da 500ms in `LinkManager` per
`refresh_broken_links()`, invece di chiamarlo ad ogni `textChanged`.

### D.3 — Settings dialog lazy pages

Costruire le pagine del dialog solo quando vengono selezionate (usando un flag
`_page_built: list[bool]`).

### D.4 — Update check in QThread

Spostare `requests.get` di `check_for_update()` in un QThread con signal
`update_available`.

---

## Ordine di Esecuzione

| Step | Phase | Rischio |
|---|---|---|
| 1 | D.1 — Doppio anchor map | Basso |
| 2 | D.2 — Debounce broken links | Basso |
| 3 | D.4 — Update check async | Basso |
| 4 | A — Anteprima principale async | Medio |
| 5 | B — Link preview async universale | Medio |
| 6 | C — Search replace async | Basso |
| 7 | D.3 — Settings lazy | Medio |

---

*Piano completato il 27 Giugno 2026*
