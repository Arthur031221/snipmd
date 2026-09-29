"""Image in, clean text out. Shared by the CLI, the menu bar app and the server."""

from __future__ import annotations

import logging
import math
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from snipmd import backends, postprocess, vision
from snipmd.config import MODES, Config

log = logging.getLogger("snipmd")

MIN_SIDE = 448
MAX_SIDE = 2560


class InputError(ValueError):
    pass


@dataclass
class Result:
    text: str
    raw: str
    mode: str
    backend: str
    seconds: float

    def to_dict(self) -> dict:
        return asdict(self)


def prepare_image(src: Path, workdir: Path) -> Path:
    """Flatten transparency, pad the edges and upscale tiny crops.

    A tight crop around one equation often has glyphs touching the border and
    may be under 100 px tall. Both hurt recognition. White padding and a
    modest integer upscale fix most of it.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(src)
        img.load()
    except FileNotFoundError as exc:
        raise InputError(f"file not found: {src}") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise InputError(f"not an image snipmd can read: {src}") from exc

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    else:
        img = img.convert("RGB")

    w, h = img.size
    if w < 4 or h < 4:
        raise InputError(f"image is too small to read ({w}x{h} px)")
    longest = max(w, h)
    if longest < MIN_SIDE:
        factor = min(4, math.ceil(MIN_SIDE / longest))
        img = img.resize((w * factor, h * factor), Image.Resampling.LANCZOS)
    elif longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        img = img.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)

    w, h = img.size
    pad = max(12, round(min(w, h) * 0.06))
    canvas = Image.new("RGB", (w + 2 * pad, h + 2 * pad), "white")
    canvas.paste(img, (pad, pad))
    out = workdir / "snipmd-input.png"
    canvas.save(out, "PNG")
    return out


class Engine:
    """Holds one backend so the model stays loaded between requests."""

    def __init__(self, cfg: Config, backend: str | None = None):
        self.cfg = cfg
        self.backend_name = backend or cfg.backend
        self._backend: backends.Backend | None = None
        self._lock = threading.Lock()

    @property
    def backend(self) -> backends.Backend:
        with self._lock:
            if self._backend is None:
                self._backend = backends.pick(self.cfg, self.backend_name)
                log.debug("using backend %s", self._backend.name)
            return self._backend

    def warm(self) -> str:
        be = self.backend
        be.load()
        return be.name

    def run(self, image: Path, mode: str | None = None) -> Result:
        """Recognise one image. ``seconds`` excludes loading the model.

        The menu bar app and the server load the model once at start, so the
        time that matters per snip is everything after that.
        """
        mode = mode or self.cfg.mode
        if mode not in MODES:
            raise InputError(f"unknown mode '{mode}'. Use one of: {', '.join(MODES)}")
        use_vision = mode == "text" and self.cfg.text_engine == "vision" and vision.available()
        if not use_vision:
            self.backend.load()
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="snipmd-") as tmp:
            prepared = prepare_image(Path(image), Path(tmp))

            if use_vision:
                try:
                    raw = vision.recognize(prepared)
                    text = postprocess.collapse_whitespace(raw)
                    return Result(text, raw, mode, "vision", time.perf_counter() - start)
                except vision.VisionUnavailable as exc:
                    log.warning("Apple Vision failed, falling back to the model: %s", exc)

            be = self.backend
            raw = be.recognize(prepared, backends.TASK_PROMPTS[mode], self.cfg.max_tokens)
        text = postprocess.clean(raw, mode, self.cfg.table_format)
        return Result(text, raw, mode, be.name, time.perf_counter() - start)
