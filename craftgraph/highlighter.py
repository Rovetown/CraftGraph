"""EasyMarkup syntax highlighter for the CraftGraph code editor.

Provides QSyntaxHighlighter-based highlighting for CustomCraft3 EasyMarkup
.txt files.  Consolidates the 8 keyword groups from the community Notepad++
UDL (``cc3_reference_files/original-source/SUBNAUTICA_TXT_Extension.xml``)
into 5 highlight categories:

  1. Block types (purple, bold) -- the 10 CC3 top-level keywords
  2. Field keys (teal) -- all recognized CC3 field names
  3. Delimiters (bold) -- ( ) , ;
  4. Quoted strings (green, italic) -- ``"..."``
  5. Comments (gray, italic) -- ``#`` to end of line

Rules are applied in order; later rules override earlier ones at the same
character positions.  This means strings and comments correctly suppress
keyword highlighting inside them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)

# -- Keyword sets --------------------------------------------------------------

BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "ModifiedRecipes",
        "AddedRecipes",
        "AliasRecipes",
        "CustomFabricators",
        "CustomCraftingTabs",
        "CustomFoods",
        "CustomFragmentCounts",
        "CustomSizes",
        "CustomBioFuels",
        "MovedRecipes",
    }
)

FIELD_KEYS: frozenset[str] = frozenset(
    {
        # ID fields
        "ItemID",
        "SpriteItemID",
        "TabID",
        "LinkedItemIDs",
        "FunctionalID",
        # Value fields
        "DisplayName",
        "Tooltip",
        "Required",
        "AmountCrafted",
        "Energy",
        "ColorTint",
        "FoodValue",
        "WaterValue",
        "OxygenValue",
        "HealthValue",
        "DecayRateMod",
        "FoodType",
        # Category fields
        "PdaGroup",
        "PdaCategory",
        "Model",
        # Structure fields
        "Ingredients",
        # Path fields
        "Path",
        "OldPath",
        "NewPath",
        "ParentTabPath",
        # Boolean/control fields
        "ForceUnlockAtStart",
        "Unlocks",
        "UnlockedBy",
        "Hidden",
        "Copied",
        "AllowedInCyclops",
        "AllowedInBase",
        "UseDrinkSound",
        # Fragment fields
        "FragmentsToScan",
        # Size fields
        "Width",
        "Height",
    }
)

# -- Error detection constants -------------------------------------------------

_STRUCTURAL_KEYS: frozenset[str] = BLOCK_TYPES | frozenset(
    {
        "Ingredients",
        "CustomCraftingTabs",
        "AddedRecipes",
        "AliasRecipes",
        "MovedRecipes",
        "CustomFoods",
    }
)

_QUOTING_FIELDS: frozenset[str] = frozenset({"DisplayName", "Tooltip"})

_ID_FIELDS: frozenset[str] = frozenset(
    {"ItemID", "TabID", "FunctionalID", "SpriteItemID"}
)

_PATH_FIELDS: frozenset[str] = frozenset(
    {"Path", "OldPath", "NewPath", "ParentTabPath"}
)

_SPACE_CHECK_FIELDS: frozenset[str] = _ID_FIELDS | _PATH_FIELDS


# -- Internal types ------------------------------------------------------------


@dataclass(frozen=True)
class _HighlightRule:
    """A compiled regex pattern paired with its display format."""

    pattern: re.Pattern[str]
    fmt: QTextCharFormat


# -- Helpers -------------------------------------------------------------------


def _make_format(
    *,
    foreground: str | None = None,
    bold: bool = False,
    italic: bool = False,
) -> QTextCharFormat:
    """Build a QTextCharFormat from simple style properties."""
    fmt = QTextCharFormat()
    if foreground is not None:
        fmt.setForeground(QColor(foreground))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


def _make_error_format() -> QTextCharFormat:
    """Build a QTextCharFormat with red wavy underline for error highlighting."""
    fmt = QTextCharFormat()
    fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
    fmt.setUnderlineColor(QColor("#CC0000"))
    return fmt


def _build_rules() -> list[_HighlightRule]:
    """Construct the ordered list of highlighting rules.

    Order matters: later rules override earlier ones at the same position.
    Keywords go first so that strings and comments can suppress them.
    """
    rules: list[_HighlightRule] = []

    # 1. Block types (dark magenta, bold)
    block_alt = "|".join(sorted(BLOCK_TYPES))
    rules.append(
        _HighlightRule(
            pattern=re.compile(rf"\b({block_alt})\s*:", re.IGNORECASE),
            fmt=_make_format(foreground="#8B008B", bold=True),
        )
    )

    # 2. Field keys (teal)
    field_alt = "|".join(sorted(FIELD_KEYS))
    rules.append(
        _HighlightRule(
            pattern=re.compile(rf"\b({field_alt})\s*:", re.IGNORECASE),
            fmt=_make_format(foreground="#007080"),
        )
    )

    # 3. Delimiters (bold, no colour override)
    rules.append(
        _HighlightRule(
            pattern=re.compile(r"[(),;]"),
            fmt=_make_format(bold=True),
        )
    )

    # 4. Quoted strings (forest green, italic) -- overrides keywords inside
    rules.append(
        _HighlightRule(
            pattern=re.compile(r'"(?:[^"\\]|\\.)*"'),
            fmt=_make_format(foreground="#228B22", italic=True),
        )
    )

    # 5. Comments (gray, italic) -- overrides everything after #
    rules.append(
        _HighlightRule(
            pattern=re.compile(r"#.*$"),
            fmt=_make_format(foreground="#808080", italic=True),
        )
    )

    return rules


# -- Highlighter ---------------------------------------------------------------


class EasyMarkupHighlighter(QSyntaxHighlighter):
    """QSyntaxHighlighter for CustomCraft3 EasyMarkup format.

    Attach to a ``QTextDocument`` (typically the document backing a
    ``QPlainTextEdit``) to get automatic syntax colouring::

        editor = QPlainTextEdit()
        highlighter = EasyMarkupHighlighter(editor.document())
    """

    _RE_COMMENT = re.compile(r"#.*$")
    _RE_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
    _RE_KEY_VALUE = re.compile(r"^(\s*)(\w+)(\s*:\s*)(.*?)(\s*)$")
    _RE_FIELD_COMMA_END = re.compile(r"^\s*(\w+)\s*:.*,\s*$")
    _RE_CLOSE_SEMI = re.compile(r"\)\s*;")
    _RE_FIELD_COLON_END = re.compile(r"^\s*(\w+)\s*:.*\S:\s*$")

    def __init__(self, parent: QTextDocument) -> None:
        super().__init__(parent)
        self._rules = _build_rules()
        self._error_fmt = _make_error_format()

    def highlightBlock(self, text: str) -> None:
        """Apply highlighting rules to a single text block."""
        # Pass 1: syntax coloring
        for rule in self._rules:
            for match in rule.pattern.finditer(text):
                self.setFormat(
                    match.start(),
                    match.end() - match.start(),
                    rule.fmt,
                )
        # Pass 2: error detection
        self._check_errors(text)

    def _comment_and_string_ranges(self, text: str) -> list[tuple[int, int]]:
        """Return (start, end) character ranges for comments and strings."""
        ranges: list[tuple[int, int]] = []
        for m in self._RE_STRING.finditer(text):
            ranges.append((m.start(), m.end()))
        for m in self._RE_COMMENT.finditer(text):
            ranges.append((m.start(), m.end()))
        return ranges

    def _in_protected_range(
        self, start: int, end: int, ranges: list[tuple[int, int]]
    ) -> bool:
        """Check if a span falls entirely within any comment/string range."""
        return any(rs <= start and end <= rend for rs, rend in ranges)

    def _check_errors(self, text: str) -> None:
        """Run error detection pass (E1-E5) after syntax coloring."""
        protected = self._comment_and_string_ranges(text)
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            return

        self._check_e1_missing_semicolon(text, stripped, protected)
        self._check_e2_comma_terminator(text, stripped, protected)
        self._check_e3_semicolon_between_entries(text, stripped, protected)

    def _strip_inline_comment(self, text: str) -> str:
        """Remove inline comment from a line, respecting quoted strings."""
        in_string = False
        escaped = False
        for i, ch in enumerate(text):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if ch == "#" and not in_string:
                return text[:i].rstrip()
        return text

    def _next_non_empty_text(self) -> str | None:
        """Return the stripped text of the next non-empty block, or None."""
        block = self.currentBlock().next()
        while block.isValid():
            txt = block.text().strip()
            if txt:
                return txt
            block = block.next()
        return None

    def _check_e1_missing_semicolon(
        self,
        text: str,
        stripped: str,
        protected: list[tuple[int, int]],
    ) -> None:
        """E1: Flag Key: Value lines missing a trailing semicolon."""
        m = self._RE_KEY_VALUE.match(text)
        if not m:
            return

        key = m.group(2)
        value = m.group(4).rstrip()

        # Strip inline comments from value before checking terminators
        value_clean = self._strip_inline_comment(value).rstrip()
        if not value_clean:
            # Key with no value -- structural keys are always fine
            if key.lower() in {k.lower() for k in _STRUCTURAL_KEYS}:
                return
            # Non-structural key with no value: not clearly an error
            last_char = stripped[-1] if stripped else ""
            if last_char in ";)(:,":
                return
            return

        # Lines ending with a valid terminator are fine.
        # Colon included so E1 defers to E4 for colon-ending lines.
        last_char = value_clean[-1]
        if last_char in ";)(,:":
            return

        # Structural key exemption: if the next non-empty line opens a block,
        # this key is a section header, not a value-bearing field.
        key_lower = key.lower()
        if key_lower in {k.lower() for k in _STRUCTURAL_KEYS}:
            next_text = self._next_non_empty_text()
            if next_text is not None and next_text.startswith("("):
                return

        # Calculate underline range (value portion only)
        value_start = m.start(4)
        value_len = len(value_clean)
        if self._in_protected_range(value_start, value_start + value_len, protected):
            return

        self.setFormat(value_start, value_len, self._error_fmt)

    def _check_e2_comma_terminator(
        self,
        text: str,
        stripped: str,
        protected: list[tuple[int, int]],
    ) -> None:
        """E2: Flag field-value lines ending with comma instead of semicolon."""
        effective = self._strip_inline_comment(text).rstrip()
        if not effective or not effective.endswith(","):
            return

        m = self._RE_FIELD_COMMA_END.match(effective + "\n")
        if not m:
            return

        key = m.group(1)
        if key.lower() not in {k.lower() for k in FIELD_KEYS}:
            return

        comma_idx = effective.rfind(",")
        if comma_idx < 0:
            return

        if self._in_protected_range(comma_idx, comma_idx + 1, protected):
            return

        self.setFormat(comma_idx, 1, self._error_fmt)

    def _check_e3_semicolon_between_entries(
        self,
        text: str,
        stripped: str,
        protected: list[tuple[int, int]],
    ) -> None:
        """E3: Flag ); when the next non-empty line starts with (."""
        m = self._RE_CLOSE_SEMI.search(text)
        if not m:
            return

        next_text = self._next_non_empty_text()
        if not next_text or not next_text.startswith("("):
            return

        semi_idx = m.end() - 1
        if self._in_protected_range(semi_idx, semi_idx + 1, protected):
            return

        self.setFormat(semi_idx, 1, self._error_fmt)
