"""Build demo/snip.gif: a textbook page becoming LaTeX.

The page is rendered with TeX (demo/page.tex). The selection and the
notification are drawn, because a screen recording needs a person at the
mouse. The recognised LaTeX and the timing are real: they come from
demo/crop.json, written by

  snipmd demo/crop.png --mode latex --json > demo/crop.json

Usage (from the repo root):
  uv run python demo/make_gif.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "bench"))

from render import render_tex  # noqa: E402

W, H = 960, 600
FPS = 12
CROP = (258, 282, 544, 356)  # selection on page.png, in page pixels
UI = "/System/Library/Fonts/HelveticaNeue.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"


def font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError:
        return ImageFont.load_default(size)


F_UI = font(UI, 15)
F_UI_B = font(UI, 15, 1)
F_SMALL = font(UI, 13)
F_CAP = font(UI, 20, 1)
F_MONO = font(MONO, 14)


def background() -> Image.Image:
    img = Image.new("RGB", (W, H), "#dfe3ea")
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        c = (int(222 - 20 * t), int(227 - 18 * t), int(235 - 12 * t))
        draw.line([(0, y), (W, y)], fill=c)
    return img


def menubar(img: Image.Image, busy: bool) -> None:
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 26], fill="#f4f4f6")
    x = 20
    for word in ("File", "Edit", "View", "Window", "Help"):
        draw.text((x, 5), word, font=F_UI, fill="#1d1d1f")
        x += int(draw.textlength(word, font=F_UI)) + 24
    icon = Image.open(ROOT / "src" / "snipmd" / "assets" / "icon.png").resize((20, 20))
    black = Image.new("RGBA", icon.size, (29, 29, 31, 255))
    img.paste(black, (W - 150, 3), icon)
    if busy:
        draw.text((W - 126, 5), "...", font=F_UI_B, fill="#1d1d1f")
    draw.text((W - 92, 5), "Tue 10:41", font=F_UI, fill="#1d1d1f")


def window(img: Image.Image, box: tuple[int, int, int, int], title: str) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [x0 + 2, y0 + 8, x1 + 2, y1 + 10], 12, fill=(0, 0, 0, 70)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img.paste(shadow, (0, 0), shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(box, 12, fill="white", outline="#c9cbd1")
    draw.rounded_rectangle([x0, y0, x1, y0 + 34], 12, fill="#ececef")
    draw.rectangle([x0, y0 + 20, x1, y0 + 34], fill="#ececef")
    draw.line([x0, y0 + 34, x1, y0 + 34], fill="#d3d4d9")
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        draw.ellipse([x0 + 14 + i * 20, y0 + 11, x0 + 26 + i * 20, y0 + 23], fill=c)
    tw = draw.textlength(title, font=F_UI)
    draw.text(((x0 + x1 - tw) / 2, y0 + 8), title, font=F_UI, fill="#4a4a4f")


def caption(img: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(img)
    tw = draw.textlength(text, font=F_CAP)
    x = (W - tw) / 2
    draw.rounded_rectangle([x - 18, H - 58, x + tw + 18, H - 20], 10, fill=(29, 29, 31))
    draw.text((x, H - 51), text, font=F_CAP, fill="white")


PAGE_BOX = (70, 50, 890, 540)
PAGE_OFFSET = (77, 50 + 34 + 4)


def page_frame(page: Image.Image, busy: bool = False) -> Image.Image:
    img = background()
    menubar(img, busy)
    window(img, PAGE_BOX, "chapter2.pdf")
    img.paste(page, PAGE_OFFSET)
    return img


def crosshair(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    for dx, dy in ((1, 0), (0, 1)):
        draw.line([x - 11 * dx, y - 11 * dy, x + 11 * dx, y + 11 * dy], fill="white", width=3)
        draw.line([x - 10 * dx, y - 10 * dy, x + 10 * dx, y + 10 * dy], fill="black", width=1)


def selection(base: Image.Image, rect: tuple[int, int, int, int], show_size: bool) -> Image.Image:
    x0, y0, x1, y1 = rect
    dim = Image.new("RGBA", base.size, (0, 0, 0, 90))
    ImageDraw.Draw(dim).rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 0))
    out = base.convert("RGBA")
    out.alpha_composite(dim)
    draw = ImageDraw.Draw(out)
    draw.rectangle([x0, y0, x1, y1], outline="white", width=1)
    crosshair(draw, x1, y1)
    if show_size:
        label = f"{(x1 - x0) * 2}  {(y1 - y0) * 2}"
        draw.text(
            (x1 + 14, y1 + 8),
            label,
            font=F_SMALL,
            fill="white",
            stroke_width=2,
            stroke_fill="black",
        )
    return out.convert("RGB")


def notification(base: Image.Image, title: str, body: str, slide: float) -> Image.Image:
    out = base.copy()
    w, h = 340, 78
    x = int(W - 14 - w * slide)
    y = 38
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([x, y + 4, x + w, y + h + 4], 14, fill=(0, 0, 0, 60))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    out.paste(shadow, (0, 0), shadow)
    draw = ImageDraw.Draw(out)
    draw.rounded_rectangle([x, y, x + w, y + h], 14, fill="#f7f7f9", outline="#d6d7dc")
    draw.text((x + 16, y + 12), title, font=F_UI_B, fill="#1d1d1f")
    text = body if len(body) <= 40 else body[:37] + "..."
    draw.text((x + 16, y + 40), text, font=F_MONO, fill="#3a3a3f")
    return out


def wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split(" "):
        candidate = f"{cur} {word}" if cur else word
        if len(candidate) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = candidate
    lines.append(cur)
    return lines


def editor_frame(latex: str, typed: int, rendered: Image.Image | None) -> Image.Image:
    img = background()
    menubar(img, False)
    box = (70, 50, 890, 540)
    window(img, box, "notes.md")
    draw = ImageDraw.Draw(img)
    src = "$$\n" + latex + "\n$$"
    shown = src[:typed]
    y = 110
    for raw_line in shown.split("\n"):
        for line in wrap(raw_line, 86):
            draw.text((100, y), line, font=F_MONO, fill="#1d1d1f")
            y += 22
    if rendered is not None:
        draw.line([100, y + 16, 860, y + 16], fill="#e2e3e7")
        draw.text((100, y + 28), "rendered", font=F_SMALL, fill="#8a8a90")
        img.paste(rendered, (100, y + 52))
    return img


def main() -> None:
    data = json.loads((HERE / "crop.json").read_text())
    latex, seconds = data["text"], data["seconds"]
    page = Image.open(HERE / "page.png").convert("RGB")
    page = page.crop((0, 0, page.width, min(page.height, PAGE_BOX[3] - PAGE_OFFSET[1] - 2)))
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required: brew install ffmpeg")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        rendered_png = render_tex(f"$\\displaystyle {latex}$", tmp / "pred.png", tmp / "tex", 2.5)
        rendered = Image.open(rendered_png).convert("RGB")

        frames: list[Image.Image] = []

        def hold(img: Image.Image, secs: float) -> None:
            frames.extend([img] * max(1, round(secs * FPS)))

        base = page_frame(page)
        hold(base, 1.0)
        f = base.copy()
        caption(f, "Press cmd+shift+2")
        hold(f, 1.0)

        ox, oy = PAGE_OFFSET
        x0, y0, x1, y1 = CROP[0] + ox, CROP[1] + oy, CROP[2] + ox, CROP[3] + oy
        start = base.copy()
        crosshair(ImageDraw.Draw(start), x0, y0)
        caption(start, "Drag a box around the equation")
        hold(start, 0.5)
        steps = 16
        for i in range(1, steps + 1):
            t = i / steps
            t = 1 - (1 - t) ** 2
            rect = (x0, y0, int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t))
            f = selection(base, rect, show_size=True)
            caption(f, "Drag a box around the equation")
            frames.append(f)
        hold(frames[-1], 0.4)

        busy = page_frame(page, busy=True)
        caption(busy, f"GLM-OCR runs on the Mac: {seconds:.2f} s")
        hold(busy, max(0.5, min(seconds, 1.5)))

        done = page_frame(page)
        title = f"LaTeX copied in {seconds:.2f} s"
        for i in range(1, 7):
            f = notification(done, title, latex, i / 6)
            caption(f, "LaTeX is on the clipboard")
            frames.append(f)
        hold(frames[-1], 1.6)

        src_len = len("$$\n" + latex + "\n$$")
        paste = editor_frame(latex, src_len, None)
        caption(paste, "Paste anywhere")
        hold(paste, 0.9)
        final = editor_frame(latex, src_len, rendered)
        caption(final, "Paste anywhere")
        hold(final, 2.8)

        for i, frame in enumerate(frames):
            frame.save(tmp / f"f{i:04d}.png")
        out = HERE / "snip.gif"
        palette = tmp / "palette.png"
        pattern = str(tmp / "f%04d.png")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(FPS),
                "-i",
                pattern,
                "-vf",
                "palettegen=max_colors=128",
                str(palette),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(FPS),
                "-i",
                pattern,
                "-i",
                str(palette),
                "-lavfi",
                "paletteuse=dither=none",
                "-loop",
                "0",
                str(out),
            ],
            check=True,
        )
        print(
            f"{out} ({len(frames)} frames, {len(frames) / FPS:.1f} s, "
            f"{out.stat().st_size // 1024} KB)"
        )


if __name__ == "__main__":
    main()
