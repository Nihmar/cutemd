# PLAN — Rendere l'applicazione più fluida e moderna

## Stato attuale (baseline)

- **~6900 LOC Python**, UI interamente QWidgets + Fusion style
- Editor `QPlainTextEdit` con syntax highlighting + find/replace + completer
- Preview `QTextBrowser` con HTML generato via `markdown-it-py`
- 9 temi via `QPalette` + QSS con placeholder `${KEY}`
- Splitter editor/preview, file tree laterale, tab multipli
- 300ms debounce sulla preview; nessuna animazione/transizione
- Single-thread: preview rendering e caricamento immagini nel thread GUI

## Problemi percepiti

1. **Preview lagga su file grandi** — `build_html` e `add_img_dimensions` (che carica `QImage` per ogni immagine) girano nel thread GUI e bloccano l'input.
2. **Nessun feedback visivo durante il caricamento** — switch di tab, apertura file, rendering preview non mostrano spinner/skeleton.
3. **Transizioni assenti** — toggle preview/file tree è istantaneo (brusco).
4. **Splitter poco raffinato** — manca collasso animato, snap laterale, overlay.
5. **Tab bar essenziale** — nessuna preview tooltip ricca, nessun indicatore di modifica colorato.
6. **Scroll sync imperfetto** — approccio a mappa lineare, non proporzionale.
7. **Settings dialog statico** — nessuna preview live del font/tema scelto.

---

## Fase 1 — Snellire il rendering (impatto immediato)

### 1.1 Preview asincrona
**Cosa**: Spostare `build_html` e `add_img_dimensions` in un `QThread` worker.  
**Come**: `PreviewWorker(QObject)` con segnali `result_ready(str)`. Il worker riceve `text, md, css, theme, font, base_dir, images_dir`. Usa `QImage` per le dimensioni (già thread-safe).  
**Impatto**: Preview non blocca più l'editor.  
**Complessità**: Media (2-3 giorni).  
**File**: `editor_tab.py`, nuovo `ui/preview_worker.py`.

### 1.2 Skeleton/spinner durante il caricamento
**Cosa**: Mostrare un placeholder animato (3 puntini pulsanti o skeleton) mentre la preview è in elaborazione.  
**Come**: `QStackedWidget` con indice 0 = spinner, indice 1 = preview. Al via del worker → spinner. A `result_ready` → swap a preview.  
**Impatto**: Feedback visivo immediato.  
**Complessità**: Bassa (1 giorno).  
**File**: `editor_tab.py`, nuovo widget spinner.

### 1.3 Debounce adattivo
**Cosa**: Ridurre il debounce a 150ms per file < 2000 linee, 500ms per file più grandi.  
**Come**: Misurare `len(text)` e regolare `setInterval()` dinamicamente.  
**Complessità**: Trascurabile.  
**File**: `editor_tab.py`.

---

## Fase 2 — Animazioni e micro-interazioni

### 2.1 Transizione toggle preview
**Cosa**: Animare l'apertura/chiusura della preview con slide orizzontale (300ms ease-out).  
**Come**: `QPropertyAnimation` sul `size` del pannello preview dentro lo splitter.  
**Complessità**: Bassa (1 giorno).  
**File**: `editor_tab.py`.

### 2.2 Transizione toggle file tree
**Cosa**: Slide laterale (200ms) invece di hide/show istantaneo.  
**Come**: `QPropertyAnimation` su `maximumWidth`/`minimumWidth`.  
**Complessità**: Bassa.  
**File**: `main_window.py`.

### 2.3 Hover feedback su file tree
**Cosa**: Sfondo con transizione fluida (non solo `:hover` istantaneo).  
**Come**: Sostituire `QTreeView` con widget custom o usare `QStyledItemDelegate` con paint animato.  
**Complessità**: Media.  
**File**: `file_tree_panel.py`.

### 2.4 Pulsanti toolbar con effetto ripple
**Cosa**: Click con effetto onda concentrica (material-like).  
**Come**: Sottoclasse `QToolButton`, `paintEvent` con `QTimeLine`.  
**Complessità**: Media (2 giorni).  
**File**: nuovo `ui/widgets.py` o `ui/ripple_button.py`.

---

## Fase 3 — Splitter e layout migliorati

### 3.1 Snap del pannello laterale
**Cosa**: Il file tree si può collassare a icon-bar (solo icone) con hover per espandere.  
**Come**: Due stati del pannello: expanded (testo + icone) / collapsed (solo icone 28px). Transizione animata tra i due.  
**Complessità**: Media (2-3 giorni).  
**File**: `main_window.py`, `file_tree_panel.py`.

### 3.2 Splitter con overlay preview
**Cosa**: Opzione "zen mode": preview a schermo intero con overlay semitrasparente dell'editor.  
**Come**: `QStackedWidget` con layer overlay, toggle via shortcut.  
**Complessità**: Bassa.  
**File**: `editor_tab.py`.

### 3.3 Tab bar migliorata
**Cosa**: 
- Icona file type (`.md`, `.jpg`, `.pdf`) nella tab
- Pallino colorato per stato "modificato"
- Tooltip con path completo e anteprima miniatura  
**Come**: `QTabWidget` con `QTabBar` custom, paint delegate.  
**Complessità**: Media.  
**File**: `main_window.py`.

---

## Fase 4 — Preview potenziata

### 4.1 Scroll sync proporzionale
**Cosa**: Mappare la posizione scroll editor→preview in modo proporzionale invece che per blocchi.  
**Come**: Calcolare il rapporto `scroll_value / scroll_max` nell'editor e applicarlo alla preview.  
**Complessità**: Bassa.  
**File**: `editor_tab.py`.

### 4.2 Preview minimap (opzionale)
**Cosa**: Mini-anteprima del markdown renderizzato a lato (tipo Sublime).  
**Come**: Seconda `QTextBrowser` in scala ridotta, sincronizzata.  
**Complessità**: Alta (3-4 giorni).  
**File**: nuovo componente.

### 4.3 Code block: copy button e linguaggio badge
**Cosa**: Pulsante "copia" su ogni blocco codice, badge col linguaggio.  
**Come**: Iniettare HTML/CSS nel rendering markdown per i blocchi `code`. Bottone gestito via `QTextBrowser` + JavaScript o via HTML puro.  
**Complessità**: Media.  
**File**: `html_builder.py`, `markdown/tools.py`.

---

## Fase 5 — Settings ed esperienza utente

### 5.1 Settings dialog con preview live
**Cosa**: Cambiare font/tema e vedere l'effetto in tempo reale.  
**Come**: Panel di preview nel dialog che reagisce ai cambiamenti.  
**Complessità**: Media.  
**File**: `settings_dialog.py`.

### 5.2 Welcome screen ridisegnato
**Cosa**: Schermata iniziale con:  
- Cartelle recenti con anteprima  
- Crea nuovo vault  
- Apri esistente  
- Tema attuale visibile  
**Come**: Ridisegnare `WelcomeDialog` con layout a card.  
**Complessità**: Media.  
**File**: `welcome_dialog.py`.

### 5.3 Shortcut bar contestuale
**Cosa**: Barra flottante in basso con shortcut del momento (es. `Ctrl+B` bold, `Tab` indent).  
**Come**: Widget semi-trasparente posizionato sopra l'editor, visibile a toggle.  
**Complessità**: Bassa.  
**File**: `editor_tab.py`.

---

## Fase 6 — Performance e architettura

### 6.1 Caricamento immagini su thread separato
**Cosa**: `add_img_dimensions` carica `QImage` per ogni immagine. Spostare il caricamento in un thread worker.  
**Come**: `ImageSizeWorker` che pre-risolve i path e carica le `QImage` in parallelo.  
**Complessità**: Media.  
**File**: `image_utils.py`, nuovo `ui/image_worker.py`.

### 6.2 Cache persistente delle dimensioni immagini
**Cosa**: Salvare `{path: (w, h)}` in `.cutemd/image_cache.json` per evitare di ricaricare `QImage` ad ogni rendering.  
**Come**: `add_img_dimensions` controlla la cache prima di chiamare `QImage`. Invalidazione via `mtime`.  
**Complessità**: Bassa.  
**File**: `image_utils.py`.

### 6.3 Lazy loading immagini nella preview
**Cosa**: Le immagini fuori dal viewport non vengono caricate subito.  
**Come**: Sfruttare il caricamento asincrono — Qt chiama `loadResource` solo per le immagini visibili. Già parzialmente in atto.  
**Complessità**: Bassa (verifica).  
**File**: `preview_browser.py`.

---

## Priorità e stima

| Fase | Impatto | Giorni | Priorità |
|---|---|---|---|
| 1.1 Preview asincrona | 🔴 Altissimo | 2-3 | **1** |
| 1.2 Spinner/skeleton | 🟠 Alto | 1 | **2** |
| 2.1 Transizione preview | 🟠 Alto | 1 | **3** |
| 2.2 Transizione file tree | 🟡 Medio | 1 | **5** |
| 3.1 Snap pannello laterale | 🟡 Medio | 2-3 | **6** |
| 5.1 Settings preview live | 🟡 Medio | 2 | **7** |
| 4.1 Scroll sync proporzionale | 🟢 Basso | 0.5 | **4** |
| 6.2 Cache dimensioni immagini | 🟢 Basso | 0.5 | **8** |
| 1.3 Debounce adattivo | 🟢 Basso | 0.2 | **9** |
| 4.3 Code block copy button | 🟢 Basso | 2 | **10** |
| 3.3 Tab bar migliorata | 🟡 Medio | 2 | **11** |
| 2.3 Hover file tree animato | 🟡 Medio | 2 | **12** |
| 2.4 Ripple buttons | 🟢 Basso | 2 | **13** |
| 5.2 Welcome screen | 🟡 Medio | 2 | **14** |
| 3.2 Zen mode overlay | 🟢 Basso | 1 | **15** |
| 4.2 Minimap preview | 🟢 Basso | 3-4 | **16** |
| 5.3 Shortcut bar | 🟢 Basso | 1 | **17** |

**Totale stimato**: ~25-30 giorni lavoro per tutte le fasi.  
**Quick win (primi 3 giorni)**: Fase 1.1 + 1.2 + 1.3 = preview asincrona con spinner.
