"""OCR backends behind one small interface.

A backend turns an image file plus a GLM-OCR task prompt into raw text. The
engine handles image preparation and post-processing, so backends stay thin.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Protocol

from snipmd.config import Config

TASK_PROMPTS = {
    "markdown": "Text Recognition:",
    "text": "Text Recognition:",
    "latex": "Formula Recognition:",
    "table": "Table Recognition:",
}


class BackendError(RuntimeError):
    """The backend exists but failed (model missing, server down, bad output)."""


class BackendUnavailable(BackendError):
    """The backend cannot run on this machine or is not set up."""


class Backend(Protocol):
    name: str

    def status(self) -> tuple[bool, str]:
        """Return (ready, human readable detail) without loading the model."""
        ...

    def load(self) -> None:
        """Load weights or check the server. Safe to call more than once."""
        ...

    def recognize(self, image: Path, prompt: str, max_tokens: int) -> str: ...


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def make(name: str, cfg: Config) -> Backend:
    if name == "mlx":
        from snipmd.backends.mlx import MlxBackend

        return MlxBackend(cfg.mlx_model)
    if name == "ollama":
        from snipmd.backends.ollama import OllamaBackend

        return OllamaBackend(cfg.ollama_model, cfg.ollama_url)
    raise BackendUnavailable(f"unknown backend '{name}'. Use mlx, ollama or auto.")


def pick(cfg: Config, name: str | None = None) -> Backend:
    """Resolve ``auto`` to a concrete backend.

    Order: MLX with the model already downloaded, then Ollama with the model
    already pulled, then MLX (downloads on first use). A backend that needs a
    download is only chosen when nothing is ready.
    """
    name = name or cfg.backend
    if name != "auto":
        return make(name, cfg)

    reasons = []
    mlx = make("mlx", cfg) if is_apple_silicon() else None
    if mlx is not None:
        ready, detail = mlx.status()
        if ready:
            return mlx
        reasons.append(f"mlx: {detail}")
    else:
        reasons.append("mlx: needs a Mac with Apple Silicon")

    ollama = make("ollama", cfg)
    ready, detail = ollama.status()
    if ready:
        return ollama
    reasons.append(f"ollama: {detail}")

    if mlx is not None and mlx.can_download():  # type: ignore[attr-defined]
        return mlx

    raise BackendUnavailable(
        "no OCR backend is ready.\n  "
        + "\n  ".join(reasons)
        + f"\nFix one of them, for example `ollama pull {cfg.ollama_model}`, "
        "or run `snipmd pull`."
    )
