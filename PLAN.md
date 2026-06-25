# PLAN — Migrazione UI dichiarativa (.py → .ui)

**Versione target:** 1.0.0  
**Autore:** CuteMD contributors  
**Data:** 2026-06-25  

---

## 1. Scopo e obiettivi

Migrare la UI di CuteMD da widget creati programmaticamente in Python a file `.ui` dichiarativi, editabili con **Qt Designer**. I vantaggi attesi:

- Separazione netta tra struttura visuale (`.ui`) e logica applicativa (`.py`).
- Modifica rapida del layout senza toccare codice.
- Possibilità per contributor non-sviluppatori di contribuire al design.
- `retranslateUi()` generato automaticamente per le traduzioni statiche.

### Cosa NON si vuole ottenere

- **Non** una migrazione totale: molti componenti sono procedurali per natura (tab dinamici, menu data-driven, custom paint) e forzarli in `.ui` sarebbe controproducente.
- **Non** la perdita della compatibilità con l'attuale sistema di theming QSS e traduzioni.

---

## 2. Analisi di fattibilità per file

| File | Widget | Fattibilità `.ui` | Note |
|---|---|---|---|
| `main_window.py` | `MainWindow` | **Parziale** | Shell statico convertibile; tab e azioni restano procedurali |
| `editor_tab.py` | `EditorTab`, `LineNumberArea` | **Bassa** | ~15 widget ma logica complessa (thread, timer, custom paint) |
| `editor_toolbar.py` | `EditorToolbar` | **Media** | Bottoni generati da dati; menu heading procedurale |
| `file_tree_panel.py` | `FileTreePanel`, `_FileTreeView` | **Bassa** | QTreeView custom con drag-drop, F2/Delete |
| `find_bar.py` | `FindBar` | **Alta** | Tutti widget statici — candidato ideale |
| `settings_dialog.py` | `SettingsDialog`, `_FontPicker` | **Media** | Sezioni condizionali + tabella shortcut con cell widget dinamici |
| `welcome_dialog.py` | `WelcomeDialog` | **Alta** | 90% statico |
| `search_panel.py` | `SearchPanel` | **Alta** | Struttura statica; risultati popolati proceduralmente |
| `toc_panel.py` | `TocPanel` | **Alta** | Un solo `CuteListWidget` |
| `link_preview_popup.py` | `LinkPreviewPopup` | **Media** | Widget semplici ma window flags atipici |
| `image_viewer.py` | `ImageViewer` | **Alta** | QLabel in QScrollArea |
| `pdf_viewer.py` | `PdfViewer` | **Alta** | Barra navigazione statica + scroll area |
| `shortcuts_dialog.py` | `ShortcutsDialog` | **Alta** (shell) | Righe tabella popolate proceduralmente |
| `editor_context_menu.py` | (funzione) | **Impossibile** | Menu interamente procedurale |

### Riepilogo

- **5 file** ad alta fattibilità: `FindBar`, `WelcomeDialog`, `TocPanel`, `ImageViewer`, `PdfViewer`
- **4 file** a media fattibilità: `EditorToolbar`, `SettingsDialog`, `LinkPreviewPopup`, `SearchPanel`
- **4 file** a bassa fattibilità: `MainWindow`, `EditorTab`, `FileTreePanel`, `ShortcutsDialog`
- **1 file** impossibile: `EditorContextMenu`
- **2 file** non applicabili: `CuteListWidget` (sottoclasse), `PreviewTextBrowser` (sottoclasse)

---

## 3. Strategia di migrazione in 4 fasi

### Fase 1 — Pilota: componenti semplici (1-2 giorni)

Convertire i file a più alta fattibilità per validare il flusso di lavoro:

1. **`FindBar`** → `ui/forms/find_bar.ui`  
   - 100% statico, ~10 widget.
   - Primo test di `QUiLoader` + connessione segnali + `retranslateUi()` + QSS.

2. **`WelcomeDialog`** → `ui/forms/welcome_dialog.ui`  
   - Gestione del caso condizionale (`recent_label` + `_recent_list`): creare entrambi i widget nel `.ui`, nasconderli se non ci sono cartelle recenti.

3. **`TocPanel`** → `ui/forms/toc_panel.ui`  
   - Un solo `CuteListWidget` promosso. Verifica del flusso dei promoted widget.

**Obiettivo fase 1:** Definire lo stack tecnico (loader, convenzioni, pattern di connessione) e validarlo su casi semplici.

---

### Fase 2 — Componenti a media complessità (3-5 giorni)

4. **`SearchPanel`** → `ui/forms/search_panel.ui`  
   - Struttura statica (2 QLineEdit, 2 QPushButton, QCheckBox, QLabel, CuteListWidget).  
   - Sfida: le liste dei risultati sono popolate proceduralmente — nessun impatto sul `.ui`.

5. **`SettingsDialog`** — parziale  
   - Le pagine statiche (Language, Theme, Editor, Preview Font, Storage) possono essere convertite.  
   - Le pagine condizionali (Shortcuts, Sync) restano in Python con widget creati a runtime.  
   - **Sfida:** il `_FontPicker` è un custom widget composito (QLineEdit + QListWidget). Va registrato come promoted widget e creato nel `.ui`? O creato ancora via codice dentro il dialog?
   - **Decisione:** le pagine statiche vanno in `.ui`; `_FontPicker` rimane creato via codice e inserito nel layout tramite placeholder.

6. **`EditorToolbar`** — parziale  
   - Il container (`QWidget` con `objectName="editorToolbar"`) e il layout `QHBoxLayout` con spacing vanno nel `.ui`.  
   - I bottoni sono generati da `TOOLBAR_ITEMS` in un loop — restano in Python.  
   - **Sfida:** il layout `.ui` deve avere un placeholder (es. `QWidget` vuoto o layout con nome) dove il codice Python inserisce i bottoni.

7. **`LinkPreviewPopup`** → `ui/forms/link_preview_popup.ui`  
   - Widget interni (QLabel header, QPlainTextEdit editor, QLabel immagine) sono statici.  
   - Window flags e attributi (`FramelessWindowHint`, `WA_ShowWithoutActivating`) si impostano in Python dopo il load.

---

### Fase 3 — Componenti complessi (5-8 giorni)

8. **`MainWindow`** — shell statico  
   - Il guscio esterno va in `ui/forms/main_window.ui`:  
     - `QMainWindow` + `centralWidget`  
     - Layout orizzontale: `_left_tb` (QWidget, `objectName="leftToolbar"`) | `_splitter` (QSplitter)  
     - Dentro lo splitter: `_left_stack` (QStackedWidget) | `editor_pane` (QWidget con QVBoxLayout)  
     - Status bar inline (`objectName="inlineStatusBar"`)  
   - Tutto ciò che è dinamico resta in Python: tab, azioni, menu, timer, connessioni.  
   - **Sfida:** `QMainWindow` ha metodi built-in (`menuBar()`, `statusBar()`, `setCentralWidget()`) che Qt Designer gestisce nativamente. Il nostro `status_widget` inline è custom — va aggiunto come widget normale, non come `QStatusBar`.

9. **`PdfViewer`** → `ui/forms/pdf_viewer.ui`  
   - Barra navigazione completamente statica (QPushButton × 3, QLabel, QCheckBox × 2, QButtonGroup).  
   - Il `QScrollArea` con la `QLabel` interna per il rendering delle pagine.  
   - Segnali e shortcut restano in Python.

10. **`ImageViewer`** → `ui/forms/image_viewer.ui`  
    - Triviale: QLabel dentro QScrollArea.

---

### Fase 4 — Pulizia e consolidamento (2-3 giorni)

11. **Rimozione codice obsoleto:** eliminare dai `.py` la creazione dei widget ora in `.ui`.
12. **Verifica QSS:** tutti gli `objectName` critici (`leftToolbar`, `editorToolbar`, `toolbarSep`, `inlineStatusBar`, `sectionList`) devono essere preservati nei `.ui`.
13. **Verifica traduzioni:** ogni `.ui` produce `retranslateUi()`. Il sistema attuale usa `changeEvent(LanguageChange)` + `retranslate()` custom. Vanno armonizzati.
14. **Build system:** aggiornare `scripts/build_windows.bat`, `build_windows.sh`, `build_appimage.sh` per includere i `.ui` file via `--add-data "ui/forms;ui/forms"`.
15. **Test manuale completo** su tutti i dialog e pannelli convertiti.

---

## 4. Stack tecnico

### 4.1 Caricamento `.ui`

Opzione A — `PySide6.QtUiTools.QUiLoader` (runtime, senza compilazione):

```python
from PySide6.QtUiTools import QUiLoader
loader = QUiLoader()
widget = loader.load("ui/forms/find_bar.ui", parent)
```

- **Pro:** nessun passo di build aggiuntivo. Modifica il `.ui` e riavvia.
- **Contro:** carica a runtime (overhead trascurabile per file piccoli). I promoted widget vanno registrati prima del load.

Opzione B — `pyside6-uic` (compilazione a `.py`):

```bash
pyside6-uic ui/forms/find_bar.ui -o ui/forms/find_bar_ui.py
```

- **Pro:** nessuna dipendenza runtime da `QtUiTools`. Nessun overhead di parsing XML.
- **Contro:** richiede un passo di build. Modifiche al `.ui` richiedono ricompilazione.

**Decisione:** **Opzione A** (`QUiLoader`). Per un progetto di queste dimensioni, la semplicità di sviluppo prevale. Il parsing XML è istantaneo per file < 50 KB. Si può aggiungere un wrapper `load_ui(name)` con caching.

### 4.2 `_resolve_path()` per PyInstaller

I file `.ui` devono essere accessibili sia in sviluppo che nel bundle congelato:

```python
import sys
from pathlib import Path

def _resolve_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return str(base / relative_path)
```

Il wrapper `load_ui()` userà `_resolve_path()` per localizzare i file `.ui`.

### 4.3 Promoted widgets

Per usare `CuteListWidget`, `_FileTreeView`, `LineNumberArea`, ecc. nei `.ui`:

```python
from PySide6.QtUiTools import QUiLoader
from ui.widgets import CuteListWidget

# Prima di caricare qualsiasi .ui che usa CuteListWidget
loader = QUiLoader()
loader.registerCustomWidget(CuteListWidget)
```

In Qt Designer, si aggiunge un `QListWidget` e lo si promuove a `CuteListWidget` specificando:
- **Promoted class name:** `CuteListWidget`
- **Header file:** `ui.widgets`

### 4.4 Connessione segnali

Pattern proposto per connettere segnali dopo il load:

```python
class FindBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        loader = QUiLoader()
        loader.load(_resolve_path("ui/forms/find_bar.ui"), self)

        # Riferimenti ai widget (creati dal loader come figli di self)
        self._input = self.findChild(QLineEdit, "_input")
        self._case_btn = self.findChild(QToolButton, "_case_btn")
        # ...

        # Connessioni
        self._input.textChanged.connect(self._on_find_text_changed)
        self._case_btn.toggled.connect(self._highlight_all)
```

**Alternativa:** usare `findChild` con `objectName` (più robusto del nome variabile, che non sopravvive al `.ui`).

D'ora in poi, ogni widget messo in un `.ui` **deve** avere un `objectName` univoco. Questo già accade per i widget critici (toolbar, status bar, section list). Va esteso a tutti.

### 4.5 Traduzioni

Qt Designer genera stringhe marcate per `retranslateUi()`. Il pattern attuale:

```python
def changeEvent(self, event):
    if event.type() == QEvent.Type.LanguageChange:
        self.retranslate()
```

Va esteso per chiamare `self.retranslateUi(self)` (metodo generato) **oppure** il nostro `retranslate()` custom.  
**Decisione:** mantenere il nostro metodo `retranslate()` e NON dipendere dal `retranslateUi()` generato. Le stringhe nei `.ui` saranno marcate con `self.tr()` come sempre; il file `.ui` viene editato a mano o via Designer per mantenere le chiavi di traduzione.

---

## 5. Sfide tecniche e soluzioni

### 5.1 Widget condizionali (SettingsDialog)

**Problema:** Le pagine Shortcuts e Sync esistono solo quando `folder_settings is not None`. In un `.ui` non si può esprimere questa condizione.

**Soluzione:** Creare un `.ui` con solo le pagine statiche. Le pagine condizionali vengono aggiunte a runtime con `stack.addWidget(widget)`, esattamente come oggi. Il `QStackedWidget` e la `QListWidget` di navigazione sono nel `.ui`; gli indici condizionali vanno calcolati in Python.

### 5.2 Tabella shortcut con cell widget (`QKeySequenceEdit`)

**Problema:** `QTableWidget` con widget dentro le celle (`setCellWidget`) non si rappresenta in `.ui`.

**Soluzione:** La tabella vuota (3 colonne, header) è nel `.ui`. Le righe e i `QKeySequenceEdit` sono aggiunti in Python, come oggi.

### 5.3 `_FontPicker` (widget composito)

**Problema:** È un `QWidget` contenente `QLineEdit` + `QListWidget`. Non ha un equivalente nativo in Qt Designer.

**Soluzione:** Registrare `_FontPicker` come promoted widget. Posizionare un `QWidget` placeholder nel `.ui` e promuoverlo.  
**Alternativa:** Non metterlo nel `.ui` — crearlo in Python e inserirlo nel layout via `form.setWidget(row, role, picker)`.

### 5.4 Menu e azioni (`QAction`)

**Problema:** `QMainWindow` in `.ui` può contenere `QAction`, ma le nostre 23 azioni sono create in `_setup_actions()` e hanno shortcut dinamici (il `ShortcutManager` può sovrascriverli).

**Soluzione:** Le azioni **non** vanno nel `.ui`. Restano in Python perché:
- Gli shortcut sono mutabili (per-folder overrides).
- Le connessioni a `triggered`/`toggled` sono complesse.
- Il `ShortcutManager` itera su `_all_actions` dict.

### 5.5 `EditorToolbar` con bottoni data-driven

**Problema:** I 12+ bottoni sono creati in un loop da `TOOLBAR_ITEMS`. Metterli staticamente nel `.ui` distruggerebbe la data-driven nature.

**Soluzione:** Il container (`editorToolbar`) e il layout `QHBoxLayout` vanno nel `.ui`. I bottoni sono aggiunti in Python come oggi. Il layout `.ui` è accessibile via `self.layout()`.

### 5.6 Custom subclasses con overridden events

**Problema:** `_FileTreeView` (QTreeView con `keyPressEvent`, `dragEnterEvent`, ecc.), `LineNumberArea` (QWidget con `paintEvent`), `PreviewTextBrowser` (QTextBrowser con `anchorClicked`).

**Soluzione:** Questi NON vanno nei `.ui`. Sono creati in Python e inseriti via codice. Nei `.ui` che li contengono, si usa un placeholder `QWidget` promosso alla sottoclasse custom.

---

## 6. Convenzioni

### 6.1 Nomenclatura file

```
ui/
├── forms/                    # Directory per i file .ui
│   ├── main_window.ui
│   ├── find_bar.ui
│   ├── welcome_dialog.ui
│   ├── search_panel.ui
│   ├── toc_panel.ui
│   ├── settings_dialog.ui
│   ├── link_preview_popup.ui
│   ├── pdf_viewer.ui
│   └── image_viewer.ui
├── widgets.py                # Custom widget subclasses
├── load_ui.py                # Wrapper QUiLoader con caching + _resolve_path
└── ...                       # File esistenti
```

### 6.2 `objectName` obbligatorio

Ogni widget referenziato da Python via `findChild()` **deve** avere un `objectName` nel `.ui`.  
Pattern di naming: `snake_case` descrittivo, coerente col nome dell'attributo Python (es. `search_input`, `case_btn`).

### 6.3 Layout

I layout nei `.ui` devono avere `objectName` solo se referenziati da Python (es. per aggiungere widget a runtime).  
Margini e spacing: specificati nel `.ui`, non in Python. Eventuali override runtime vanno giustificati da un commento.

---

## 7. Stima tempi

| Fase | Attività | Giorni |
|---|---|---|
| 1 | Pilota: FindBar, WelcomeDialog, TocPanel | 2 |
| 2 | SearchPanel, SettingsDialog (parziale), EditorToolbar, LinkPreviewPopup | 5 |
| 3 | MainWindow shell, PdfViewer, ImageViewer | 5 |
| 4 | Pulizia, QSS, traduzioni, build system, test | 3 |
| **Totale** | | **15 giorni** |

Con buffer per imprevisti: **3-4 settimane**.

---

## 8. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| `QUiLoader` incompatibile con PyInstaller | Alto | Test nella Fase 1 con build Windows + AppImage |
| Regressione QSS per `objectName` persi | Medio | Checklist di verifica in Fase 4; test visuale su tutti i temi |
| Traduzioni rotte (`self.tr()` non chiamato su widget da `.ui`) | Medio | Il `.ui` non forza `tr()` automatico — vanno marcate a mano o si tiene `retranslate()` custom |
| Aumento complessità percepita per nuovi contributor | Basso | Il `.ui` è più accessibile del codice Python per modifiche di layout |
| Performance di `QUiLoader` all'avvio | Basso | Caricamento XML di file < 20 KB è < 1ms; caching dei loader evita parsing duplicati |

---

## 9. Build system

### 9.1 PyInstaller

Aggiungere a tutti e tre gli script di build:

```
--add-data "ui/forms;ui/forms"
```

### 9.2 Sviluppo

Nessuna modifica: `uv run main.py` continua a funzionare. I `.ui` sono nella directory `ui/forms/`.

### 9.3 CI/CD

Se in futuro verrà aggiunta CI, si può validare i `.ui` con:

```bash
pyside6-uic --help  # verifica presenza tool
python -c "from PySide6.QtUiTools import QUiLoader"  # verifica modulo
```

---

## 10. Checklist di completamento

- [ ] Tutti i file `.ui` nella directory `ui/forms/` con `objectName` su ogni widget referenziato
- [ ] `ui/load_ui.py` con wrapper `load_ui(name)` + `_resolve_path()` + caching
- [ ] `CuteListWidget`, `_FontPicker`, `LineNumberArea`, `_FileTreeView`, `PreviewTextBrowser` registrati come promoted widget
- [ ] Tutti i `findChild()` usano `objectName`, non nomi variabile Python
- [ ] I 4 `objectName` QSS critici preservati: `leftToolbar`, `inlineStatusBar`, `editorToolbar`, `toolbarSep`, `sectionList`
- [ ] `changeEvent` / `LanguageChange` testato su tutti i widget da `.ui`
- [ ] Build Windows (`.exe`) testata con `--add-data "ui/forms;ui/forms"`
- [ ] Build AppImage testata
- [ ] Test manuale: aprire ogni dialog, cambiare lingua, cambiare tema, ridimensionare
- [ ] Codice Python di creazione widget rimosso (solo per i file completamente migrati)
