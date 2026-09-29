"""LaTeX normalisation and scoring for the round trip benchmark.

Normalisation removes differences that do not change the rendered math:
whitespace, thin spaces, \\left and \\right, \\displaystyle, braces around a
single sub or superscript token, and a few spelling variants (\\le vs \\leq).
Everything else counts as an error, including \\mathrm{d} vs d.
"""

from __future__ import annotations

import re

SYNONYMS = {
    r"\dfrac": r"\frac",
    r"\tfrac": r"\frac",
    r"\le": r"\leq",
    r"\ge": r"\geq",
    r"\ne": r"\neq",
    r"\rightarrow": r"\to",
    r"\lbrace": r"\{",
    r"\rbrace": r"\}",
    r"\vert": "|",
    r"\lvert": "|",
    r"\rvert": "|",
    r"\mid": "|",
    r"\Vert": r"\|",
    r"\lVert": r"\|",
    r"\rVert": r"\|",
}

DROP = (
    r"\displaystyle",
    r"\textstyle",
    r"\left",
    r"\right",
    r"\bigl",
    r"\bigr",
    r"\Bigl",
    r"\Bigr",
    r"\big",
    r"\Big",
    r"\quad",
    r"\qquad",
)

_SPACES = {"\\,", "\\;", "\\:", "\\!", "\\ "}
_TOKEN = r"(\\[A-Za-z]+|\\.|[^\s{}\\])"


def _replace_command(text: str, cmd: str, new: str) -> str:
    # Match the command only when it is not the prefix of a longer name.
    return re.sub(re.escape(cmd) + r"(?![A-Za-z])", lambda _m: new, text)


def normalize(latex: str) -> str:
    s = latex.strip()
    for cmd in DROP:
        s = _replace_command(s, cmd, "")
    # Drop thin spaces token by token so the second backslash of \\ survives.
    s = "".join(t for t in re.findall(r"\\[A-Za-z]+|\\.|.", s, re.DOTALL) if t not in _SPACES)
    for old, new in SYNONYMS.items():
        s = _replace_command(s, old, new)
    s = re.sub(r"\\operatorname\{(\w+)\}", r"\\\1", s)
    s = re.sub(r"\s+", "", s)
    # ^{x} -> ^x and _{\alpha} -> _\alpha when the group holds one token.
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"([_^])\{" + _TOKEN + r"\}", r"\1\2", s)
    # A trailing period or comma is punctuation, not math.
    s = re.sub(r"[.,]$", "", s)
    return s


OPERATORS = (
    "max",
    "min",
    "sin",
    "cos",
    "tan",
    "log",
    "ln",
    "exp",
    "det",
    "lim",
    "sup",
    "inf",
    "arg",
    "dim",
    "ker",
    "gcd",
    "deg",
    "Pr",
)
_FENCES = (("(", ")", "pmatrix"), ("[", "]", "bmatrix"), ("|", "|", "vmatrix"))


def equivalent(latex: str) -> str:
    """Stricter normalisation plus rewrites between constructs that render alike.

    Applied on top of :func:`normalize`. Each rule maps two spellings of the
    same printed formula to one form:
    - an ``array`` inside ``( )``, ``[ ]`` or ``| |`` becomes pmatrix,
      bmatrix or vmatrix, and an ``array`` after ``\\{`` closed by ``.``
      becomes ``cases``
    - ``^{\\prime}`` becomes ``'``
    - ``\\mathrm{max}`` and ``\\operatorname{max}`` become ``\\max``
    """
    s = normalize(latex)
    for lo, rc, env in _FENCES:
        pattern = re.escape(lo) + r"\\begin\{array\}\{[lcr|]+\}(.*?)\\end\{array\}" + re.escape(rc)
        s = re.sub(pattern, lambda m, e=env: f"\\begin{{{e}}}{m.group(1)}\\end{{{e}}}", s)
    s = re.sub(
        r"\\\{\\begin\{array\}\{[lcr|]+\}(.*?)\\end\{array\}\.?(?!\\\})",
        lambda m: f"\\begin{{cases}}{m.group(1)}\\end{{cases}}",
        s,
    )
    s = re.sub(r"\^\{\\prime\\prime\}|\^\\prime\^\\prime", "''", s)
    s = re.sub(r"\^\{\\prime\}|\^\\prime", "'", s)
    ops = "|".join(OPERATORS)
    s = re.sub(r"\\(?:mathrm|operatorname)\{(" + ops + r")\}", r"\\\1", s)
    # Rewrites can leave single-token groups such as _{\max}. Normalise again.
    return normalize(s)


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(pred: str, truth: str) -> dict:
    p, t = normalize(pred), normalize(truth)
    edits = levenshtein(p, t)
    pe, te = equivalent(pred), equivalent(truth)
    return {
        "exact": p == t,
        "equivalent": pe == te,
        "edits": edits,
        "length": len(t),
        "cer": edits / max(1, len(t)),
        "edits_equiv": levenshtein(pe, te),
        "length_equiv": len(te),
        "pred_norm": p,
        "truth_norm": t,
    }
