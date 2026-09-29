"""Local HTTP API for editor integrations.

Binds to 127.0.0.1 only. Requests that carry a browser Origin other than
localhost are refused, so a web page you visit cannot drive the API.

Endpoints:
  GET  /health            {"ok": true, "version": ..., "backend": ...}
  POST /ocr?mode=latex    body: raw image bytes, or JSON {"image": base64, "mode": ...}
  POST /snip?mode=latex   opens the crosshair on this Mac, returns the result
  GET  /history?n=20      recent entries
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from snipmd import __version__, history, system
from snipmd.backends import BackendError
from snipmd.config import MODES
from snipmd.engine import Engine, InputError

log = logging.getLogger("snipmd")

MAX_BODY = 25 * 1024 * 1024
_ALLOWED_ORIGINS = ("http://localhost", "http://127.0.0.1", "null")


def _origin_ok(origin: str | None) -> bool:
    if not origin:
        return True
    return any(origin == o or origin.startswith(o + ":") for o in _ALLOWED_ORIGINS)


class Handler(BaseHTTPRequestHandler):
    server_version = f"snipmd/{__version__}"
    engine: Engine
    snip_lock = threading.Lock()

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s %s", self.address_string(), fmt % args)

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._send(status, {"error": message})

    def _guard(self) -> bool:
        if not _origin_ok(self.headers.get("Origin")):
            self._error(HTTPStatus.FORBIDDEN, "cross-origin requests are not allowed")
            return False
        return True

    def do_GET(self) -> None:
        if not self._guard():
            return
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/health":
            self._send(
                HTTPStatus.OK,
                {"ok": True, "version": __version__, "backend": self.engine.backend_name},
            )
        elif url.path == "/history":
            try:
                n = int(query.get("n", ["20"])[0])
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "n must be an integer")
                return
            self._send(HTTPStatus.OK, {"entries": [e.__dict__ for e in history.recent(n)]})
        else:
            self._error(HTTPStatus.NOT_FOUND, f"no route {url.path}")

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "image larger than 25 MB")
            return None
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:
        if not self._guard():
            return
        url = urlparse(self.path)
        query = parse_qs(url.query)
        mode = query.get("mode", [None])[0]
        if url.path == "/ocr":
            body = self._read_body()
            if body is None:
                return
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype == "application/json":
                try:
                    data = json.loads(body or b"{}")
                    image = base64.b64decode(data.get("image", ""), validate=True)
                except (json.JSONDecodeError, binascii.Error, AttributeError):
                    self._error(HTTPStatus.BAD_REQUEST, "expected JSON with a base64 'image'")
                    return
                mode = data.get("mode", mode)
            else:
                image = body
            if not image:
                self._error(HTTPStatus.BAD_REQUEST, "empty request body, send image bytes")
                return
            self._run(image, mode, source="api")
        elif url.path == "/snip":
            self._snip(mode)
        else:
            self._error(HTTPStatus.NOT_FOUND, f"no route {url.path}")

    def _run(self, image: bytes, mode: str | None, source: str) -> None:
        if mode is not None and mode not in MODES:
            self._error(HTTPStatus.BAD_REQUEST, f"mode must be one of {', '.join(MODES)}")
            return
        with tempfile.TemporaryDirectory(prefix="snipmd-api-") as tmp:
            path = Path(tmp) / "upload.png"
            path.write_bytes(image)
            status, payload = self._recognize(path, mode, source)
        self._send(status, payload)

    def _recognize(self, path: Path, mode: str | None, source: str) -> tuple[int, dict]:
        cfg = self.engine.cfg
        try:
            result = self.engine.run(path, mode)
        except InputError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        except BackendError as exc:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)}
        entry = history.add(
            text=result.text,
            mode=result.mode,
            backend=result.backend,
            seconds=result.seconds,
            source=source,
            image=path,
            limit=cfg.history_limit,
            keep_image=cfg.keep_images,
        )
        payload = result.to_dict()
        payload["id"] = entry.id
        return HTTPStatus.OK, payload

    def _snip(self, mode: str | None) -> None:
        if mode is not None and mode not in MODES:
            self._error(HTTPStatus.BAD_REQUEST, f"mode must be one of {', '.join(MODES)}")
            return
        if not self.snip_lock.acquire(blocking=False):
            self._error(HTTPStatus.CONFLICT, "a snip is already in progress")
            return
        # The lock is released before the response goes out, so a client can
        # start the next snip as soon as it has the answer.
        try:
            with tempfile.TemporaryDirectory(prefix="snipmd-snip-") as tmp:
                try:
                    shot = system.capture_region(Path(tmp) / "snip.png")
                except system.CaptureError as exc:
                    status, payload = HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)}
                else:
                    if shot is None:
                        status, payload = HTTPStatus.OK, {"cancelled": True}
                    else:
                        status, payload = self._recognize(shot, mode, "api-snip")
        finally:
            self.snip_lock.release()
        self._send(status, payload)


def make_server(engine: Engine, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("SnipHandler", (Handler,), {"engine": engine})
    return ThreadingHTTPServer((host, port), handler)
