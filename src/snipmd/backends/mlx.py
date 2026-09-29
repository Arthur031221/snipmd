"""MLX backend. Runs GLM-OCR in process through mlx-vlm on Apple Silicon."""

from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from snipmd.backends import BackendError, BackendUnavailable, is_apple_silicon


def _mlx_vlm_installed() -> bool:
    return importlib.util.find_spec("mlx_vlm") is not None


class MlxBackend:
    name = "mlx"

    def __init__(self, model: str):
        self.model_id = model
        self._model = None
        self._processor = None
        self._config = None
        # MLX streams belong to the thread that created them. A model loaded
        # on one thread and called from another fails with "There is no
        # Stream(gpu, N) in current thread". The app, the server and the CLI
        # call from different threads, so every MLX call runs on this one.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="snipmd-mlx")

    def _local_path(self) -> Path | None:
        path = Path(self.model_id).expanduser()
        if path.is_dir() and (path / "config.json").exists():
            return path
        return None

    def is_downloaded(self) -> bool:
        if self._local_path():
            return True
        try:
            from huggingface_hub import try_to_load_from_cache
        except ImportError:
            return False
        found = try_to_load_from_cache(self.model_id, "model.safetensors")
        return isinstance(found, str)

    def can_download(self) -> bool:
        return is_apple_silicon() and _mlx_vlm_installed()

    def status(self) -> tuple[bool, str]:
        if not is_apple_silicon():
            return False, "needs a Mac with Apple Silicon"
        if not _mlx_vlm_installed():
            return False, "mlx-vlm is not installed (pip install mlx-vlm)"
        if not self.is_downloaded():
            return False, f"{self.model_id} not downloaded yet. Run `snipmd pull`."
        return True, self.model_id

    def cached_path(self) -> Path | None:
        """Local snapshot folder, found without touching the network."""
        local = self._local_path()
        if local:
            return local
        try:
            from huggingface_hub import snapshot_download
            from huggingface_hub.utils import disable_progress_bars

            disable_progress_bars()
            return Path(snapshot_download(self.model_id, local_files_only=True))
        except Exception:
            return None

    def pull(self) -> Path:
        if self._local_path():
            return self._local_path()  # type: ignore[return-value]
        from huggingface_hub import snapshot_download

        return Path(snapshot_download(self.model_id))

    def load(self) -> None:
        self._worker.submit(self._load).result()

    def _load(self) -> None:
        if self._model is not None:
            return
        if not is_apple_silicon():
            raise BackendUnavailable("the mlx backend needs a Mac with Apple Silicon")
        if not _mlx_vlm_installed():
            raise BackendUnavailable("mlx-vlm is not installed. Run `pip install mlx-vlm`.")
        from mlx_vlm import load

        # Load from the local snapshot when there is one. Passing the repo
        # id makes huggingface_hub check for updates online on every start.
        source = self.cached_path() or self.model_id
        try:
            self._model, self._processor = load(str(source))
        except Exception as exc:
            raise BackendError(f"could not load {self.model_id}: {exc}") from exc
        self._config = getattr(self._model, "config", None)

    def recognize(self, image: Path, prompt: str, max_tokens: int) -> str:
        return self._worker.submit(self._recognize, image, prompt, max_tokens).result()

    def _recognize(self, image: Path, prompt: str, max_tokens: int) -> str:
        self._load()
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        formatted = apply_chat_template(self._processor, self._config, prompt, num_images=1)
        try:
            out = generate(
                self._model,
                self._processor,
                formatted,
                [str(image)],
                max_tokens=max_tokens,
                temperature=0.0,
                verbose=False,
            )
        except Exception as exc:
            raise BackendError(f"mlx-vlm generation failed: {exc}") from exc
        return out if isinstance(out, str) else str(getattr(out, "text", out))
