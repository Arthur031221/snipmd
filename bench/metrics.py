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

_TOKEN = r"(\\[A-Za-z]+|\\.|[^\s{}\\])"


def _replace_command(text: str, cmd: str, new: str) -> str:
    # Match the command only when it is not the prefix of a longer name.
    return re.sub(re.escape(cmd) + r"(?![A-Za-z])", lambda _m: new, text)


def normalize(latex: str) -> str:
    s = latex.strip()
    for cmd in DROP:
        s = _replace_command(s, cmd, "")
    s = re.sub(r"\\[,;:! ]", "", s)
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
    return {
        "exact": p == t,
        "edits": edits,
        "length": len(t),
        "cer": edits / max(1, len(t)),
        "pred_norm": p,
        "truth_norm": t,
    }
