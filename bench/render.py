"""Render LaTeX to PNG for the benchmark.

Prefers a real TeX engine (tectonic, then pdflatex) so matrices and cases
render the way they do in a paper. Falls back to matplotlib mathtext, which
cannot draw matrix environments, so those equations are skipped in that mode.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

PREAMBLE = r"""\documentclass[border=6pt,12pt]{standalone}
\usepackage{amsmath,amssymb,amsfonts}
\begin{document}
"""

MATHTEXT_UNSUPPORTED = ("\\begin{", "\\binom", "\\oint", "\\iint", "\\mathbb", "\\|")


class RenderError(RuntimeError):
    pass


def engine() -> str:
    if shutil.which("tectonic"):
        return "tectonic"
    if shutil.which("pdflatex"):
        return "pdflatex"
    return "mathtext"


def _pdf_to_png(pdf: Path, png: Path, scale: float) -> None:
    import Quartz
    from Foundation import NSURL

    doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(str(pdf)))
    if doc is None:
        raise RenderError(f"cannot open {pdf}")
    page = Quartz.CGPDFDocumentGetPage(doc, 1)
    box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
    w, h = int(box.size.width * scale), int(box.size.height * scale)
    space = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(
        None, w, h, 8, 0, space, Quartz.kCGImageAlphaPremultipliedLast
    )
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, ((0, 0), (w, h)))
    Quartz.CGContextScaleCTM(ctx, scale, scale)
    Quartz.CGContextDrawPDFPage(ctx, page)
    image = Quartz.CGBitmapContextCreateImage(ctx)
    dest = Quartz.CGImageDestinationCreateWithURL(
        NSURL.fileURLWithPath_(str(png)), "public.png", 1, None
    )
    Quartz.CGImageDestinationAddImage(dest, image, None)
    if not Quartz.CGImageDestinationFinalize(dest):
        raise RenderError(f"cannot write {png}")


def render_tex(body: str, png: Path, workdir: Path, scale: float = 2.0) -> Path:
    """Compile a LaTeX body with a TeX engine and rasterise page one."""
    workdir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(body.encode()).hexdigest()[:12]
    tex = workdir / f"{key}.tex"
    tex.write_text(PREAMBLE + body + "\n\\end{document}\n", encoding="utf-8")
    pdf = workdir / f"{key}.pdf"
    if pdf.exists():
        _pdf_to_png(pdf, png, scale)
        return png
    tool = engine()
    if tool == "tectonic":
        cmd = ["tectonic", "--chatter", "minimal", "--outdir", str(workdir), str(tex)]
    elif tool == "pdflatex":
        cmd = ["pdflatex", "-interaction=nonstopmode", "-output-directory", str(workdir), str(tex)]
    else:
        raise RenderError("no TeX engine found")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not pdf.exists():
        raise RenderError((proc.stderr or proc.stdout).strip()[-400:])
    _pdf_to_png(pdf, png, scale)
    return png


def render_equation(latex: str, png: Path, workdir: Path, scale: float = 2.0) -> Path:
    if engine() == "mathtext":
        return render_mathtext(latex, png)
    return render_tex(f"$\\displaystyle {latex}$", png, workdir, scale)


def mathtext_supported(latex: str) -> bool:
    return not any(token in latex for token in MATHTEXT_UNSUPPORTED)


def render_mathtext(latex: str, png: Path, dpi: int = 200) -> Path:
    if not mathtext_supported(latex):
        raise RenderError("mathtext cannot render this equation")
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, f"${latex}$", fontsize=14)
    try:
        fig.savefig(png, dpi=dpi, bbox_inches="tight", pad_inches=0.08, facecolor="white")
    except ValueError as exc:
        raise RenderError(str(exc)) from exc
    finally:
        plt.close(fig)
    return png
