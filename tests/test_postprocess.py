from snipmd import postprocess as pp


def test_strip_whole_fence():
    assert pp.strip_code_fences("```markdown\nhello\n```") == "hello"
    assert pp.strip_code_fences("```\nx = 1\n```") == "x = 1"


def test_keep_code_fence_inside_prose():
    text = "Run this:\n\n```python\nprint(1)\n```\n\nDone."
    assert pp.strip_code_fences(text) == text


def test_unwrap_packaging_fence_inside_prose():
    text = "Intro\n```latex\n\\alpha\n```"
    assert pp.strip_code_fences(text) == "Intro\n\\alpha"


def test_normalize_delimiters():
    assert pp.normalize_delimiters(r"\( x \)") == "$x$"
    assert pp.normalize_delimiters("\\[\n x^2 \n\\]") == "$$x^2$$"
    assert pp.normalize_delimiters("a $ x + y $ b") == "a $x + y$ b"
    assert pp.normalize_delimiters("$$ \\sum_i x_i $$") == "$$\\sum_i x_i$$"


def test_normalize_leaves_dollar_amounts_alone():
    assert pp.normalize_delimiters("costs \\$5 and \\$10") == "costs \\$5 and \\$10"


def test_collapse_whitespace_keeps_indent():
    text = "a   b  \n\n\n\n  - item   one\r\n"
    assert pp.collapse_whitespace(text) == "a b\n\n  - item one"


def test_to_latex_strips_delimiters():
    assert pp.to_latex("$$\n\\frac{a}{b}\n$$") == "\\frac{a}{b}"
    assert pp.to_latex("\\[ x^2 + y^2 = z^2 \\]") == "x^2 + y^2 = z^2"
    assert pp.to_latex("$\\alpha$") == "\\alpha"
    assert pp.to_latex("```latex\n\\beta\n```") == "\\beta"


def test_to_latex_strips_equation_env():
    raw = "\\begin{equation}\n  E = mc^2\n\\end{equation}"
    assert pp.to_latex(raw) == "E = mc^2"


def test_to_latex_keeps_matrix_env_and_joins_lines():
    raw = "$$\n\\begin{pmatrix}\na & b \\\\\nc & d\n\\end{pmatrix}\n$$"
    assert pp.to_latex(raw) == "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}"


def test_to_latex_multiple_blocks_are_gathered():
    out = pp.to_latex("$$a=1$$\n$$b=2$$")
    assert out == "\\begin{gathered} a=1 \\\\ b=2 \\end{gathered}"


def test_to_latex_empty():
    assert pp.to_latex("   ") == ""


def test_html_table_to_markdown():
    html = "<table><tr><th>Name</th><th>Qty</th></tr><tr><td>a|b</td><td>2</td></tr></table>"
    assert pp.to_table(html) == "| Name | Qty |\n| --- | --- |\n| a\\|b | 2 |"


def test_html_table_colspan_and_br():
    html = "<table><tr><td colspan='2'>Head</td></tr><tr><td>1<br>x</td><td>2</td></tr></table>"
    assert pp.table_rows(html) == [["Head", ""], ["1 x", "2"]]


def test_table_to_csv_quotes():
    html = "<table><tr><td>a, b</td><td>c</td></tr></table>"
    assert pp.to_table(html, "csv") == '"a, b",c'


def test_markdown_table_roundtrip():
    md = "| a | b |\n|---|:--:|\n| 1 | 2 |"
    assert pp.table_rows(md) == [["a", "b"], ["1", "2"]]
    assert pp.to_table(md, "csv") == "a,b\n1,2"


def test_table_ragged_rows_are_padded():
    md = "| a | b | c |\n| --- | --- | --- |\n| 1 |"
    assert pp.table_rows(md) == [["a", "b", "c"], ["1", "", ""]]


def test_table_mode_falls_back_to_text():
    assert pp.to_table("just words") == "just words"


def test_markdown_converts_inline_html_table():
    raw = "Intro\n<table><tr><td>1</td><td>2</td></tr></table>\nEnd"
    assert pp.to_markdown(raw) == "Intro\n\n| 1 | 2 |\n| --- | --- |\n\nEnd"


def test_to_text_drops_markup():
    raw = "## Heading\n\nSome **bold** and *it* text."
    assert pp.to_text(raw) == "Heading\n\nSome bold and it text."


def test_clean_dispatch():
    assert pp.clean("$$x$$", "latex") == "x"
    assert pp.clean("\\(x\\)", "markdown") == "$x$"
    assert pp.clean("**a**", "text") == "a"
    assert pp.clean("| a |\n| --- |", "table", "csv") == "a"
