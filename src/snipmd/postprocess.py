"""Clean raw model output into something you can paste.

GLM-OCR tends to wrap output in code fences, mixes ``\\[ \\]`` with ``$$``,
emits tables as HTML and pads inline math with spaces that break Obsidian and
GitHub rendering. Everything here is pure string work so it is easy to test.
"""

from __future__ import annotations

import csv
import io
import re
from html.parser import HTMLParser

_FENCE_RE = re.compile(r"^\s*```[\w+-]*[ \t]*\n(.*?)\n?```\s*$", re.DOTALL)
_INNER_FENCE_RE = re.compile(r"```[\w+-]*[ \t]*\n(.*?)\n?```", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Remove a code fence that wraps the whole output.

    Fences inside the text are kept when there is real prose around them,
    because a snip of a code listing should stay a code block. Fences tagged
    as markdown, latex, math or html are always unwrapped: the model uses them
    as packaging, not content.
    """
    text = text.strip()
    match = _FENCE_RE.match(text)
    if match:
        return match.group(1).strip()

    def unwrap(m: re.Match[str]) -> str:
        tag = m.group(0).split("\n", 1)[0].strip("`").strip().lower()
        if tag in ("markdown", "md", "latex", "tex", "math", "html"):
            return m.group(1)
        return m.group(0)

    return _INNER_FENCE_RE.sub(unwrap, text).strip()


def trim_repetition(text: str, max_unit: int = 400) -> str | None:
    """Detect a generation loop at the end of ``text``.

    Returns the text with the loop collapsed to one copy, or None when the
    tail does not repeat. A unit must repeat 3 times (5 times when shorter
    than 16 characters) so that honest repetition, such as two identical
    table rows, is left alone.
    """
    n = len(text)
    for p in range(1, min(max_unit, n // 3) + 1):
        reps = 3 if p >= 16 else 5
        if p * reps > n:
            continue
        unit = text[n - p :]
        if unit.strip() and text.endswith(unit * reps):
            # Walk back to where the loop began and keep exactly one period
            # from there, so the kept copy starts where the model started it.
            start = n - p * reps
            while start > 0 and text[start - 1] == text[start - 1 + p]:
                start -= 1
            return text[: start + p]
    return None


def drop_empty_fences(text: str) -> str:
    """Remove fences with nothing inside and a fence left open at the end."""
    text = re.sub(r"```[\w+-]*[ \t]*\n\s*```[ \t]*\n?", "", text)
    if text.count("```") % 2 == 1:
        head, _, tail = text.rpartition("```")
        if not tail.strip() or tail.strip().isalnum():
            text = head
    return text


def normalize_delimiters(text: str) -> str:
    """Use ``$...$`` for inline math and ``$$...$$`` for display math."""
    text = re.sub(r"\\\[\s*(.*?)\s*\\\]", lambda m: f"$${m.group(1)}$$", text, flags=re.DOTALL)
    text = re.sub(r"\\\(\s*(.*?)\s*\\\)", lambda m: f"${m.group(1)}$", text, flags=re.DOTALL)

    # Display math: trim the padding inside $$ ... $$.
    text = re.sub(r"\$\$\s*(.*?)\s*\$\$", lambda m: f"$${m.group(1)}$$", text, flags=re.DOTALL)

    # Inline math: `$ x $` does not render in Obsidian or on GitHub.
    def trim_inline(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        return f"${inner}$" if inner else m.group(0)

    parts = re.split(r"(\$\$.*?\$\$)", text, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if not part.startswith("$$"):
            parts[i] = re.sub(r"(?<![\\$])\$(?!\$)([^$\n]+?)(?<!\\)\$(?!\$)", trim_inline, part)
    return "".join(parts)


def collapse_whitespace(text: str) -> str:
    """Trim line ends, squeeze inner runs of spaces and extra blank lines.

    Leading indentation is kept because it carries meaning in Markdown lists
    and code blocks.
    """
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.replace("\t", "    ").rstrip()
        indent = len(line) - len(line.lstrip(" "))
        body = re.sub(r" {2,}", " ", line[indent:])
        lines.append(" " * indent + body)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


_LATEX_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|\s+|.", re.DOTALL)
_TEXT_COMMANDS = {"\\text", "\\textrm", "\\textbf", "\\textit", "\\textsf", "\\mbox"}


def _wordish(tok: str) -> bool:
    return tok[:1].isalnum() or (tok.startswith("\\") and tok[1:2].isalpha())


def _keep_space(prev: str, nxt: str) -> bool:
    if prev in ("&", "\\\\") or nxt in ("&", "\\\\"):
        return True
    return (_wordish(prev) or prev == "}") and _wordish(nxt)


def tidy_latex(latex: str) -> str:
    """Drop the token spacing GLM-OCR emits, e.g. ``\\frac {a + b}{c}``.

    Math mode ignores spaces, so this never changes the rendering. The result
    reads like hand-written LaTeX: no spaces around braces, scripts and
    operators, one space between words (``\\sin x``, ``} e``) and around
    ``&`` and ``\\\\``. A space between a command and a letter is never
    removed, since that would merge them. Spaces inside ``\\text{...}`` stay.
    """
    tokens = _LATEX_TOKEN.findall(latex)
    out: list[str] = []
    text_depth: list[int] = []
    depth = 0
    pending_text = False
    for i, tok in enumerate(tokens):
        if tok.isspace():
            if text_depth:
                out.append(" ")
                continue
            prev = out[-1] if out else ""
            nxt = next((t for t in tokens[i + 1 :] if not t.isspace()), "")
            if prev and nxt and _keep_space(prev, nxt):
                out.append(" ")
            continue
        if tok in _TEXT_COMMANDS:
            pending_text = True
        elif tok == "{":
            depth += 1
            if pending_text:
                text_depth.append(depth)
            pending_text = False
        elif tok == "}":
            if text_depth and text_depth[-1] == depth:
                text_depth.pop()
            depth -= 1
        elif pending_text and not tok.isspace():
            pending_text = False
        out.append(tok)
    return "".join(out).strip()


def tidy_math_spans(text: str) -> str:
    """Apply :func:`tidy_latex` inside every ``$...$`` and ``$$...$$`` span."""
    text = re.sub(
        r"\$\$(.+?)\$\$", lambda m: f"$${tidy_latex(m.group(1))}$$", text, flags=re.DOTALL
    )
    parts = re.split(r"(\$\$.*?\$\$)", text, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if not part.startswith("$$"):
            parts[i] = re.sub(
                r"(?<![\\$])\$(?!\$)([^$\n]+?)(?<!\\)\$(?!\$)",
                lambda m: f"${tidy_latex(m.group(1))}$",
                part,
            )
    return "".join(parts)


_WRAPPERS = ("equation", "equation*", "displaymath", "math")


def _strip_one(eq: str) -> str:
    eq = eq.strip()
    for left, right in (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$")):
        if eq.startswith(left) and eq.endswith(right) and len(eq) >= len(left) + len(right):
            eq = eq[len(left) : len(eq) - len(right)].strip()
            break
    for env in _WRAPPERS:
        begin, end = f"\\begin{{{env}}}", f"\\end{{{env}}}"
        if eq.startswith(begin) and eq.endswith(end):
            eq = eq[len(begin) : len(eq) - len(end)].strip()
            break
    return eq


def to_latex(text: str) -> str:
    """Return a bare equation with no math delimiters, on one line."""
    text = strip_code_fences(drop_empty_fences(text))
    text = normalize_delimiters(text)
    blocks = [b.strip() for b in re.findall(r"\$\$(.*?)\$\$", text, flags=re.DOTALL)]
    # A model that loops repeats the same block. Keep one copy.
    blocks = [b for i, b in enumerate(blocks) if i == 0 or b != blocks[i - 1]]
    leftover = re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL).strip()
    if blocks and leftover.startswith("$$") and "$$" not in leftover[2:]:
        # An unclosed block after complete ones is output cut off mid-loop.
        leftover = ""
    if blocks and leftover in blocks:
        # The same equation once bare and once in $$ is a repeat, not two parts.
        leftover = ""
    if blocks and not leftover:
        eqs = [_strip_one(b) for b in blocks if b.strip()]
    else:
        eqs = [_strip_one(text)]
    eqs = [tidy_latex(e) for e in eqs if e.strip()]
    if not eqs:
        return ""
    if len(eqs) == 1:
        return eqs[0]
    return "\\begin{gathered} " + " \\\\ ".join(eqs) + " \\end{gathered}"


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._span = 1
        self._pending: dict[int, tuple[str, int]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            attr = dict(attrs)
            try:
                self._span = max(1, int(attr.get("colspan") or 1))
            except ValueError:
                self._span = 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append(value)
            self._row.extend([""] * (self._span - 1))
            self._cell = None
            self._span = 1
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def html_table_rows(html: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return _pad(parser.rows)


def markdown_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") and line.count("|") < 1:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip("|"))]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and any(cells):
            continue
        rows.append([c.replace("\\|", "|") for c in cells])
    return _pad(rows)


def _pad(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    def fmt(row: list[str]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in row) + " |"

    lines = [fmt(rows[0]), "| " + " | ".join("---" for _ in rows[0]) + " |"]
    lines += [fmt(r) for r in rows[1:]]
    return "\n".join(lines)


def rows_to_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().rstrip("\n")


def table_rows(text: str) -> list[list[str]]:
    text = strip_code_fences(drop_empty_fences(text))
    if "<table" in text.lower() or "<tr" in text.lower():
        return html_table_rows(text)
    return markdown_table_rows(text)


def to_table(text: str, fmt: str = "markdown") -> str:
    rows = table_rows(text)
    if not rows:
        # Not a table after all. Hand back the cleaned text rather than nothing.
        return to_markdown(text)
    rows = [[tidy_math_spans(normalize_delimiters(c)) for c in r] for r in rows]
    return rows_to_csv(rows) if fmt == "csv" else rows_to_markdown(rows)


def to_markdown(text: str) -> str:
    text = strip_code_fences(drop_empty_fences(text))
    if "<table" in text.lower():
        text = re.sub(
            r"<table.*?</table>",
            lambda m: "\n\n" + rows_to_markdown(html_table_rows(m.group(0))) + "\n\n",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    text = tidy_math_spans(normalize_delimiters(text))
    return collapse_whitespace(text)


def to_text(text: str) -> str:
    """Plain text: drop Markdown emphasis and heading markers, keep line breaks."""
    text = to_markdown(text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    return collapse_whitespace(text)


def clean(text: str, mode: str, table_format: str = "markdown") -> str:
    if mode == "latex":
        return to_latex(text)
    if mode == "table":
        return to_table(text, table_format)
    if mode == "text":
        return to_text(text)
    return to_markdown(text)
