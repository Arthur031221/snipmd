import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

from equations import EQUATIONS
from metrics import levenshtein, normalize, score


def test_at_least_40_equations_in_every_category():
    assert len(EQUATIONS) >= 40
    cats = {c for c, _ in EQUATIONS}
    assert {"fraction", "integral", "matrix", "sum", "greek"} <= cats


def test_normalize_ignores_cosmetic_differences():
    assert normalize(r"\int_{0}^{1} x^{2} \, dx") == normalize(r"\int_0^1x^2dx")
    assert normalize(r"\left( 1+\frac{1}{n} \right)^{n}") == normalize(r"(1+\frac{1}{n})^n")
    assert normalize(r"\dfrac{a}{b}") == normalize(r"\frac{a}{b}")
    assert normalize(r"x \le y") == normalize(r"x\leq y")
    assert normalize(r"\displaystyle E=mc^2 .") == "E=mc^2"
    assert normalize(r"\lambda_{\max}") == r"\lambda_\max"


def test_normalize_keeps_real_differences():
    assert normalize(r"\mathrm{d}x") != normalize("dx")
    assert normalize(r"x^{2n}") == "x^{2n}"
    assert normalize(r"\leftarrow") != normalize(r"\left")


def test_levenshtein():
    assert levenshtein("", "abc") == 3
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("same", "same") == 0


def test_score():
    s = score(r"\frac{a}{b}", r"\frac{a}{ b }")
    assert s["exact"] and s["cer"] == 0
    s = score(r"\frac{a}{c}", r"\frac{a}{b}")
    assert not s["exact"] and s["edits"] == 1


def test_row_separator_survives_spacing_removal():
    assert normalize(r"a & b \\ c & d") == r"a&b\\c&d"
    assert normalize(r"x\,y\;z\!w") == "xyzw"


def test_equivalent_forms():
    from metrics import equivalent

    assert equivalent(r"\left(\begin{array}{cc} a & b \\ c & d \end{array}\right)") == equivalent(
        r"\begin{pmatrix}a&b\\c&d\end{pmatrix}"
    )
    assert equivalent(r"\left\{\begin{array}{ll} x & x>0 \\ 0 & x \le 0 \end{array}\right.") == (
        equivalent(r"\begin{cases}x&x>0\\0&x\leq0\end{cases}")
    )
    assert equivalent(r"f^{\prime}(x)") == equivalent("f'(x)")
    assert equivalent(r"\lambda_{\mathrm{max}}") == equivalent(r"\lambda_{\max}")
    assert equivalent(r"\begin{pmatrix}a\end{pmatrix}") != equivalent(
        r"\begin{bmatrix}a\end{bmatrix}"
    )
