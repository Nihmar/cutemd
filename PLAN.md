# CuteMD — Piano di sviluppo

## v0.9.6+ — Gap analysis & miglioramenti

### ✨ Features mancanti

| # | Feature | Perché |
|---|---------|--------|
| 1 | **Autosave / backup** | Non esiste autosave. Se l'app crasha, le modifiche non salvate vanno perse. Un backup automatico ogni N minuti nel `.cutemd/` sarebbe un bel safety net. |
| 2 | **Tab drag & reorder** | `QTabWidget` supporta nativamente il drag-reorder con `setMovable(True)`. Basta una riga. |
| 3 | **Undo/Redo globals** | L'undo è per-tab. Se chiudi un tab, lo storico undo muore. Niente "global undo stack" o cronologia dei file chiusi. |
| 4 | **Auto-indent / code fence completation** | `markdown_completer.py` fa auto-pair di delimitatori e continuation delle liste, ma non auto-completa code fence (```). |
| 5 | **Spell check** | Nessun spell checker. `QTextEdit` può integrarsi con Sonnet/Hunspell via dictionary, ma non è implementato. |
| 6 | **Multi-cursor / column editing** | L'editor è `QPlainTextEdit` standard — niente multi-selezione tipo Sublime/VS Code. |
| 7 | **Tab size configurabile** | Il tab stop è hardcodato a 40px (`setTabStopDistance(40)`). Potrebbe essere una preferenza utente. |
| 8 | **Word count aggiornato in tempo reale** | `_status_words` mostra il conteggio parole, ma va aggiornato solo su `_emit_status` — forse non in tempo reale durante la digitazione. |

### 🔧 Miglioramenti UI/UX

| # | Miglioramento | Dettaglio |
|---|---------------|-----------|
| 1 | **Hover link preview estesa** | Il `LinkPreviewPopup` ora mostra file markdown (testo), immagini e PDF. Manca il supporto per altri formati: **CSV** (tabella), **JSON/XML** (formattati). |
| 2 | **History / file recenti** | C'è `recent_folders` nel welcome dialog, ma non c'è una lista di **file recenti** nel menu File. |
| 3 | **Minimap / scrollbar outline** | La scrollbar dell'editor mostra solo la posizione. Una mappa del contenuto (stile Sublime/Obsidian) non c'è. |
| 4 | **Preview lazy render** | Il preview si aggiorna ogni 300ms — per file molto lunghi, questo può essere pesante. Già c'è `PreviewWorker` in thread separato, ma non c'è debounce intelligente che salti i render quando l'utente sta ancora scrivendo velocemente. |
| 5 | **Split orientation** | Lo split editor/preview è solo orizzontale. Potrebbe essere verticale (opzione). |
| 6 | **Indentazione delle liste nel preview** | Il preview HTML non mostra indentazione per liste annidate (nested lists). `html_builder.py` usa `<ul>`/`<ol>` standard, ma senza stili di indentazione. |
| 7 | **Backlinks / outgoing links panel** | I wikilink `[[...]]` vengono risolti al click, ma non c'è un pannello "backlinks" che mostra quali file linkano al corrente. |
| 8 | **File tree: multi-select / drag** | `file_tree_panel.py` usa `QListWidget` — supporta click singolo per aprire e doppio click per nuova tab, ma non drag & drop per spostare file. |

### 🐞 Bug / issue minori

| # | Problema | Note |
|---|----------|------|
| 1 | **Sync progress: parentesi `)}))` ** | Nel `_on_progress` callback di `main_window.py`, la linea `self._status_sync.setText(self.tr("Sync: {}").format(msg))` ha parens in eccesso (`)}))`). |
| 2 | **`QVariantAnimation` importato ma non usato** | In `editor_tab.py`, `QVariantAnimation` è importato ma mai utilizzato (dead code). |
| 3 | **Hardcoded shortcut key** | In `main_window.py`, `Ctrl+Shift+S` per WebDAV sync è hardcodato sia nell'azione che in `shortcuts_dialog.py` — duplicazione di informazione. |
| 4 | **`_preview_pending_preview_params` undefined** | In `_update_preview` (editor_tab.py L637), `self._pending_preview_params` viene usato nel ramo `if self._preview_busy:` ma non è inizializzato in `__init__` — funziona solo perché viene settato prima dell'uso, ma è fragile. |

### 🧹 Pulizia tecnica

| # | Cosa | Note |
|---|------|------|
| 1 | **Import inutili** | `main_window.py`: `QColor` è importato ma si potrebbe sostituire con accesso diretto. Varie import dead in `editor_tab.py`: `QVariantAnimation`, `QKeySequence`, `QShortcut`, `QTextDocument`, `QHBoxLayout`, `QLineEdit`. |
| 2 | **`_restore_last_folder` → QTimer singleShot** | Uso di `QTimer.singleShot(0, self._restore_last_folder)` per evitare race condition all'avvio. Funziona ma è un po' un hack — meglio spostare la logica in `showEvent`. |
| 3 | **Test assenti** | Come da `AGENTS.md`, non ci sono test. Per una codebase di questa dimensione, anche un test di smoke (import + creazione widget) sarebbe utile per il CI. |
| 4 | **Traduzioni incomplete** | Ci sono file `.ts` in `resources/translations/`, ma alcune stringhe in `editor_context_menu.py` e `shortcuts_dialog.py` non hanno `self.tr()`. |

### 🎯 Priorità suggerita

1. **Tab drag-reorder** — `self._tabs.setMovable(True)` (una riga)
2. **Backlinks pannello** — cerca wikilink `[[nomefile]]` negli altri file della cartella
3. **Test CI** — almeno `uv run python -c "from ui.editor_tab import EditorTab"` in GitHub Actions
