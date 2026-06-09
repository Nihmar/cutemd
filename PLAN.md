# Markdown Editor – Project Specification for AI Agent

## 1. Overview
Build a **non‑WYSIWYG** desktop Markdown editor with:
- A source code editor pane (raw Markdown) with **syntax highlighting**.
- A **live preview** pane (rendered HTML).
- No rich text editing – strictly separated editing/preview.

## 2. Tech Stack
| Component         | Technology                                           |
|-------------------|------------------------------------------------------|
| GUI framework     | PySide6 (Qt6 for Python)                            |
| Markdown parser   | `markdown-it-py` (CommonMark compliant, extensible) |
| Syntax highlight  | `pygments` (for code blocks in preview)             |
| Editor widget     | `QPlainTextEdit` (or `QTextEdit`) with custom highlighting |
| Environment       | `uv` (isolated virtual environment, no system Python) |

## 3. Core Features
- [ ] **Split pane layout** – vertical or horizontal split (user configurable)
- [ ] **Live preview** – updates on every keystroke (debounced ~200 ms)
- [ ] **Syntax highlighting** – for the raw Markdown (headings, bold, lists, code fences, links) inside the editor pane
- [ ] **File operations** – open `.md` file, save, save as, new file
- [ ] **Code block highlighting** – in the preview pane, using Pygments for fenced code blocks
- [ ] **Dark/light theme** (optional but recommended)

## 4. User Interface (Designer‑based)
- Use `pyside6-designer` to create `main_window.ui`.
- Components:
  - `QMainWindow` with menu bar (File, Edit, View).
  - Central widget: `QSplitter` containing:
    - Left: `QPlainTextEdit` (editor) – set monospaced font.
    - Right: `QTextBrowser` (preview) – displays HTML, read‑only.
- Actions: New, Open, Save, Save As, Exit, Toggle split orientation.
- Status bar: shows current line/column, word count.

## 5. Workflow for AI Agent
When asked to help with this app, the AI agent should:

1. **Initialize the environment** (user already has a git repo):
   ```bash
   uv add pyside6 markdown-it-py pygments
   ```

2. **Generate the `.ui` file** (XML) using `pyside6-designer` – or write a Python class that builds the layout manually if the agent cannot run the designer.

3. **Write the main application logic** in `main.py`:
   - Load the `.ui` file (or subclass `QMainWindow`).
   - Connect editor’s `textChanged` signal to a preview update function.
   - Use `markdown_it` + `pygments` to convert Markdown → HTML.
   - Implement file open/save.

4. **Implement editor syntax highlighting** via `QSyntaxHighlighter` subclass with rules for:
   - Headings (`#`, `##`, etc.)
   - Bold (`**text**` or `__text__`)
   - Italic (`*text*` or `_text_`)
   - Inline code (`` `code` ``)
   - Code fences (```` ``` ````)
   - Lists (`-`, `*`, `1.`)
   - Links (`[text](url)`)
   - Blockquotes (`>`)

5. **Preview rendering pipeline**:
   - Input: raw Markdown string from editor.
   - Output: HTML string.
   - Steps:
     - Parse Markdown to HTML using `markdown_it` (enable `highlight` option that calls Pygments for code blocks).
     - Wrap result in a full HTML document with minimal CSS (e.g., `github-markdown-css` or custom styles).
     - Set the HTML on `QTextBrowser` using `setHtml()`.

## 6. Example Project Structure
```
my_markdown_editor/
├── .venv/                (created by uv, ignored by git)
├── .gitignore            (add .venv, __pycache__, *.pyc)
├── pyproject.toml        (dependencies: pyside6, markdown-it-py, pygments)
├── uv.lock
├── main.py               (entry point)
├── main_window.py        (UI class – either generated or loaded from .ui)
├── main_window.ui        (optional, from designer)
├── syntax_highlighter.py (QSyntaxHighlighter subclass)
└── preview_styles.css    (custom CSS for preview)
```

## 7. Running the App
```bash
uv run main.py
```

## 8. Notes for the AI Agent
- Always use `uv run` to execute Python scripts – this respects the isolated environment.
- If generating code, prefer Python‑only layout (no external `.ui` file) for portability, but using `pyside6-uic` to compile `.ui` is acceptable.
- For syntax highlighting inside `QPlainTextEdit`, study `QSyntaxHighlighter` examples – it’s rule‑based and fast.
- The preview should handle errors gracefully (e.g., malformed Markdown → show plain text fallback).
- Debounce the preview update to avoid lag on large documents: use `QTimer` with single‑shot and 200 ms delay.
