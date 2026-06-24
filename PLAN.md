# CuteMD — Piano di sviluppo

## v0.9.6+ — Gap analysis & miglioramenti

### ✨ Features mancanti

| # | Feature | Perché |
|---|---------|--------|
| 1 | **Autosave su file esistenti** | Salvataggio automatico (es. ogni 60s) solo per file già salvati su disco (non tab "Untitled"). Previene la perdita di modifiche senza creare backup nascosti. |
| 2 | **Tab drag & reorder** | `QTabWidget` supporta nativamente il drag-reorder con `setMovable(True)`. Basta una riga. |
| 3 | **Undo/Redo globals** | L'undo è per-tab. Se chiudi un tab, lo storico undo muore. |
| 4 | **Auto-indent / code fence completation** | `markdown_completer.py` fa auto-pair di delimitatori e continuation delle liste, ma non auto-completa code fence (```). |
| 5 | **Spell check** | Nessun spell checker. `QTextEdit` può integrarsi con Sonnet/Hunspell via dictionary, ma non è implementato. |
| 6 | **Multi-cursor / column editing** | L'editor è `QPlainTextEdit` standard — niente multi-selezione tipo Sublime/VS Code. |
| 7 | **Tab size configurabile** | Il tab stop è hardcodato a 40px (`setTabStopDistance(40)`). Potrebbe essere una preferenza utente. |
| 8 | **Word count aggiornato in tempo reale** | `_status_words` mostra il conteggio parole, ma va aggiornato solo su `_emit_status`. |

### 🔧 Miglioramenti UI/UX

| # | Miglioramento | Dettaglio |
|---|---------------|-----------|
| 1 | **Hover link preview estesa** | Il `LinkPreviewPopup` ora mostra file markdown (testo), immagini e PDF. Manca il supporto per altri formati: CSV (tabella), JSON/XML (formattati). |
| 2 | **History / file recenti** | C'è `recent_folders` nel welcome dialog, ma non c'è una lista di file recenti nel menu File. |
| 3 | **Minimap / scrollbar outline** | La scrollbar dell'editor mostra solo la posizione. Una mappa del contenuto (stile Sublime/Obsidian) non c'è. |
| 4 | **Preview lazy render** | Il preview si aggiorna ogni 300ms. Per file molto lunghi può essere pesante. Già c'è `PreviewWorker` in thread separato, ma non c'è debounce intelligente. |
| 5 | **Split orientation** | Lo split editor/preview è solo orizzontale. Potrebbe essere verticale (opzione). |
| 6 | **Indentazione delle liste nel preview** | Il preview HTML non mostra indentazione per liste annidate. `html_builder.py` usa `<ul>`/`<ol>` standard, ma senza stili di indentazione. |
| 7 | **Table of Contents** | Pannello laterale con la lista degli headings del file corrente, cliccabili per navigare. |
| 8 | **File tree: multi-select / drag** | `file_tree_panel.py` usa `QListWidget` — supporta click singolo per aprire e doppio click per nuova tab, ma non drag & drop per spostare file. |

### 🐞 Bug / issue minori

| # | Problema | Note |
|---|----------|------|
| 1 | **Sync progress: parentesi in eccesso** | Nel `_on_progress` callback di `main_window.py`, la linea ha parens in eccesso. |
| 2 | **Import inutilizzati** | In `editor_tab.py`: `QVariantAnimation`, `QKeySequence`, `QShortcut`, `QTextDocument`, `QHBoxLayout`, `QLineEdit`. |
| 3 | **Hardcoded shortcut key** | `Ctrl+Shift+S` per WebDAV sync è hardcodato sia nell'azione che in `shortcuts_dialog.py`. |
| 4 | **`_preview_pending_preview_params` undefined** | In `_update_preview` (editor_tab.py), `self._pending_preview_params` non è inizializzato in `__init__`. |
| 5 | **`_restore_last_folder` con QTimer singleShot** | Hack per evitare race condition all'avvio. Meglio spostare in `showEvent`. |
| 6 | **Traduzioni incomplete** | Alcune stringhe in `editor_context_menu.py` e `shortcuts_dialog.py` non hanno `self.tr()`. |

### 🎯 Priorità suggerita

1. **Autosave su file esistenti** — timer che salva automaticamente le tab con `file_path` non nullo
2. **Table of Contents** — pannello laterale con la lista degli headings del documento corrente, cliccabili per navigare
3. **Tab drag-reorder** — `self._tabs.setMovable(True)`
4. **Pulizia import inutilizzati**
