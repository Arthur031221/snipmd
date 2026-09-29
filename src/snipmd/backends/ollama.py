"""Ollama backend. Talks to a local Ollama server over HTTP with urllib."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from snipmd.backends import BackendError, BackendUnavailable
from snipmd.postprocess import trim_repetition


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434", timeout: float = 300):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, payload: dict | None = None, timeout: float | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def installed_models(self) -> list[str]:
        try:
            tags = self._request("/api/tags", timeout=3)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise BackendUnavailable(
                f"Ollama is not reachable at {self.url} ({exc}). Start it with `ollama serve`."
            ) from exc
        return [m.get("name", "") for m in tags.get("models", [])]

    def _has_model(self, names: list[str]) -> bool:
        want = self.model if ":" in self.model else self.model + ":latest"
        return want in names

    def status(self) -> tuple[bool, str]:
        try:
            names = self.installed_models()
        except BackendUnavailable as exc:
            return False, str(exc)
        if not self._has_model(names):
            return False, f"model {self.model} not pulled. Run `ollama pull {self.model}`."
        return True, f"{self.model} at {self.url}"

    def load(self) -> None:
        ready, detail = self.status()
        if not ready:
            raise BackendUnavailable(detail)

    def pull(self) -> None:
        try:
            self._request("/api/pull", {"model": self.model, "stream": False}, timeout=3600)
        except (urllib.error.URLError, OSError) as exc:
            raise BackendError(f"ollama pull {self.model} failed: {exc}") from exc

    def recognize(self, image: Path, prompt: str, max_tokens: int) -> str:
        """Stream the answer and stop early when the model starts looping.

        The glm-ocr build in the Ollama library does not always stop at its
        end token and repeats the answer until num_predict runs out. Reading
        the stream lets us cut the loop after a few repeats instead of
        waiting for 2048 tokens.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [base64.b64encode(image.read_bytes()).decode("ascii")],
            "stream": True,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": max_tokens},
        }
        req = urllib.request.Request(
            self.url + "/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        text = ""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise BackendError(f"Ollama error: {chunk['error']}")
                    text += chunk.get("response", "")
                    if chunk.get("done"):
                        break
                    cut = trim_repetition(text)
                    if cut is not None:
                        text = cut
                        break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise BackendError(f"Ollama returned HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise BackendUnavailable(f"Ollama is not reachable at {self.url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise BackendError(f"Ollama sent a malformed stream: {exc}") from exc
        return text
