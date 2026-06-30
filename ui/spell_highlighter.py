"""Spell-check highlighter — deprecated, logic moved to syntax_highlighter.

The async SpellCheckWorker now lives in ``syntax_highlighter.py`` as
``_SpellWorker``.  This module is kept for backward-compatibility imports.
Spell-check underlines are applied by ``MarkdownHighlighter`` using a
dedicated background QThread so that ``import enchant`` never blocks the
GUI thread.
"""

from ui.syntax_highlighter import MarkdownHighlighter as _MH

# Re-export for any code that imported from here.
SpellHighlighter = _MH
