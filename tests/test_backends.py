import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from snipmd import backends
from snipmd.backends import BackendError, BackendUnavailable
from snipmd.backends.mlx import MlxBackend
from snipmd.backends.ollama import OllamaBackend
from snipmd.config import Config


class _FakeOllama(BaseHTTPRequestHandler):
    models: ClassVar[list[str]] = ["glm-ocr:q8_0"]
    requests: ClassVar[list[dict]] = []
    reply: ClassVar[dict | list] = {"response": "$$x$$", "done": True}

    def log_message(self, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json(200, {"models": [{"name": n} for n in self.models]})
        else:
            self._json(404, {"error": "nope"})

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(payload)
        if self.path == "/api/generate" and payload.get("stream"):
            chunks = self.reply if isinstance(self.reply, list) else [self.reply]
            body = "".join(json.dumps(c) + "\n" for c in chunks).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/generate":
            self._json(200, self.reply)
        elif self.path == "/api/pull":
            self._json(200, {"status": "success"})
        else:
            self._json(404, {"error": "nope"})


@pytest.fixture
def ollama_server():
    _FakeOllama.requests = []
    _FakeOllama.models = ["glm-ocr:q8_0"]
    _FakeOllama.reply = {"response": "$$x$$", "done": True}
    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_ollama_recognize_sends_image_and_prompt(ollama_server, image_file):
    be = OllamaBackend("glm-ocr:q8_0", ollama_server)
    assert be.status()[0]
    out = be.recognize(image_file, "Formula Recognition:", 123)
    assert out == "$$x$$"
    req = _FakeOllama.requests[-1]
    assert req["model"] == "glm-ocr:q8_0"
    assert req["prompt"] == "Formula Recognition:"
    assert req["stream"] is True
    assert req["options"] == {"temperature": 0, "num_predict": 123}
    assert base64.b64decode(req["images"][0]) == image_file.read_bytes()


def test_ollama_model_missing(ollama_server):
    _FakeOllama.models = ["qwen3:4b"]
    ok, detail = OllamaBackend("glm-ocr:q8_0", ollama_server).status()
    assert not ok
    assert "ollama pull glm-ocr:q8_0" in detail


def test_ollama_latest_tag_matches(ollama_server):
    _FakeOllama.models = ["glm-ocr:latest"]
    assert OllamaBackend("glm-ocr", ollama_server).status()[0]


def test_ollama_streams_and_cuts_loops(ollama_server, image_file):
    loop = [{"response": "$$\n\\frac {a}{b}\n$$\n", "done": False}] * 50
    _FakeOllama.reply = [*loop, {"response": "", "done": True}]
    out = OllamaBackend("glm-ocr:q8_0", ollama_server).recognize(image_file, "x", 10)
    assert out == "$$\n\\frac {a}{b}\n$$\n"


def test_ollama_joins_stream_chunks(ollama_server, image_file):
    _FakeOllama.reply = [
        {"response": "Hello ", "done": False},
        {"response": "world", "done": False},
        {"response": "", "done": True},
    ]
    assert OllamaBackend("glm-ocr:q8_0", ollama_server).recognize(image_file, "x", 10) == (
        "Hello world"
    )


def test_ollama_error_payload(ollama_server, image_file):
    _FakeOllama.reply = {"error": "model crashed"}
    with pytest.raises(BackendError, match="model crashed"):
        OllamaBackend("glm-ocr:q8_0", ollama_server).recognize(image_file, "x", 10)


def test_ollama_unreachable(image_file):
    be = OllamaBackend("glm-ocr:q8_0", "http://127.0.0.1:9")
    ok, detail = be.status()
    assert not ok and "not reachable" in detail
    with pytest.raises(BackendUnavailable):
        be.load()


def test_ollama_pull(ollama_server):
    OllamaBackend("glm-ocr:q8_0", ollama_server).pull()
    assert _FakeOllama.requests[-1] == {"model": "glm-ocr:q8_0", "stream": False}


def test_make_unknown():
    with pytest.raises(BackendUnavailable):
        backends.make("tesseract", Config())


class _Stub:
    def __init__(self, name, ready, downloadable=False):
        self.name = name
        self.ready = ready
        self.downloadable = downloadable

    def status(self):
        return self.ready, f"{self.name} detail"

    def can_download(self):
        return self.downloadable


def _patch(monkeypatch, apple, mlx, ollama):
    monkeypatch.setattr(backends, "is_apple_silicon", lambda: apple)
    monkeypatch.setattr(backends, "make", lambda name, cfg: mlx if name == "mlx" else ollama)


def test_auto_prefers_ready_mlx(monkeypatch):
    mlx, oll = _Stub("mlx", True), _Stub("ollama", True)
    _patch(monkeypatch, True, mlx, oll)
    assert backends.pick(Config()) is mlx


def test_auto_prefers_ready_ollama_over_download(monkeypatch):
    mlx, oll = _Stub("mlx", False, downloadable=True), _Stub("ollama", True)
    _patch(monkeypatch, True, mlx, oll)
    assert backends.pick(Config()) is oll


def test_auto_downloads_mlx_when_nothing_ready(monkeypatch):
    mlx, oll = _Stub("mlx", False, downloadable=True), _Stub("ollama", False)
    _patch(monkeypatch, True, mlx, oll)
    assert backends.pick(Config()) is mlx


def test_auto_nothing_available(monkeypatch):
    _patch(monkeypatch, False, None, _Stub("ollama", False))
    with pytest.raises(BackendUnavailable, match="no OCR backend is ready"):
        backends.pick(Config())


def test_explicit_backend_skips_auto(monkeypatch):
    oll = _Stub("ollama", False)
    _patch(monkeypatch, True, _Stub("mlx", True), oll)
    assert backends.pick(Config(), "ollama") is oll


def test_mlx_status_off_apple_silicon(monkeypatch):
    import snipmd.backends.mlx as mlx_mod

    monkeypatch.setattr(mlx_mod, "is_apple_silicon", lambda: False)
    ok, detail = MlxBackend("mlx-community/GLM-OCR-8bit").status()
    assert not ok and "Apple Silicon" in detail
    with pytest.raises(BackendUnavailable):
        MlxBackend("x").load()


def test_mlx_local_dir_counts_as_downloaded(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    assert MlxBackend(str(tmp_path)).is_downloaded()


def test_task_prompts_cover_modes():
    from snipmd.config import MODES

    assert set(backends.TASK_PROMPTS) == set(MODES)
