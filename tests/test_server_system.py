import base64
import json
import stat
import threading
import urllib.error
import urllib.request

import pytest

from snipmd import history, system
from snipmd.config import Config
from snipmd.engine import Engine
from snipmd.server import _origin_ok, make_server


@pytest.fixture
def api(fake_backend):
    server = make_server(Engine(Config()), "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health(api):
    status, body = call(api + "/health")
    assert status == 200 and body["ok"] is True


def test_ocr_raw_bytes(api, image_file):
    status, body = call(
        api + "/ocr?mode=latex", image_file.read_bytes(), {"Content-Type": "image/png"}
    )
    assert status == 200
    assert body["text"] == "\\frac{a}{b}"
    assert body["id"] == 1
    assert history.get(1).source == "api"


def test_ocr_json_body(api, image_file):
    payload = {"image": base64.b64encode(image_file.read_bytes()).decode(), "mode": "table"}
    status, body = call(
        api + "/ocr", json.dumps(payload).encode(), {"Content-Type": "application/json"}
    )
    assert status == 200 and body["mode"] == "table"


def test_ocr_errors(api, image_file):
    assert call(api + "/ocr", b"", method="POST")[0] == 400
    assert call(api + "/ocr?mode=html", image_file.read_bytes())[0] == 400
    assert call(api + "/ocr", b"garbage")[0] == 400
    bad_json = call(api + "/ocr", b"{", {"Content-Type": "application/json"})
    assert bad_json[0] == 400
    assert call(api + "/nope")[0] == 404


def test_cross_origin_refused(api, image_file):
    status, _ = call(api + "/ocr", image_file.read_bytes(), {"Origin": "https://evil.example"})
    assert status == 403


def test_history_endpoint(api, image_file):
    call(api + "/ocr?mode=latex", image_file.read_bytes())
    status, body = call(api + "/history?n=5")
    assert status == 200 and len(body["entries"]) == 1
    assert call(api + "/history?n=x")[0] == 400


def test_snip_endpoint(api, image_file, monkeypatch):
    import shutil

    def fake_capture(dest, timeout=300):
        shutil.copyfile(image_file, dest)
        return dest

    monkeypatch.setattr(system, "capture_region", fake_capture)
    status, body = call(api + "/snip?mode=latex", b"", method="POST")
    assert status == 200 and body["text"] == "\\frac{a}{b}"
    monkeypatch.setattr(system, "capture_region", lambda dest, timeout=300: None)
    assert call(api + "/snip", b"", method="POST")[1] == {"cancelled": True}


@pytest.mark.parametrize(
    "origin,ok",
    [
        (None, True),
        ("null", True),
        ("http://localhost:3000", True),
        ("http://127.0.0.1", True),
        ("http://localhost.evil.com", False),
        ("https://example.com", False),
    ],
)
def test_origin_rules(origin, ok):
    assert _origin_ok(origin) is ok


def _fake_tool(tmp_path, name, body):
    path = tmp_path / "bin" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_capture_missing_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    with pytest.raises(system.CaptureError, match="macOS"):
        system.capture_region(tmp_path / "x.png")


def test_capture_cancelled(monkeypatch, tmp_path):
    tool = _fake_tool(tmp_path, "screencapture", "exit 0")
    monkeypatch.setattr(system.shutil, "which", lambda name: str(tool))
    assert system.capture_region(tmp_path / "x.png") is None


def test_capture_permission_denied(monkeypatch, tmp_path):
    tool = _fake_tool(tmp_path, "screencapture", "echo 'could not create image from rect' >&2")
    monkeypatch.setattr(system.shutil, "which", lambda name: str(tool))
    with pytest.raises(system.CaptureError, match="Screen Recording"):
        system.capture_region(tmp_path / "x.png")


def test_capture_success(monkeypatch, tmp_path):
    tool = _fake_tool(tmp_path, "screencapture", 'printf png > "$3"')
    monkeypatch.setattr(system.shutil, "which", lambda name: str(tool))
    dest = tmp_path / "shots" / "x.png"
    assert system.capture_region(dest) == dest
    assert dest.read_text() == "png"


def test_clipboard_roundtrip(monkeypatch, tmp_path):
    sink = tmp_path / "clip.txt"
    tool = _fake_tool(tmp_path, "pbcopy", f'cat > "{sink}"')
    monkeypatch.setattr(system, "_clipboard_command", lambda: [str(tool)])
    assert system.copy_to_clipboard("\\alpha β")
    assert sink.read_text(encoding="utf-8") == "\\alpha β"


def test_clipboard_missing(monkeypatch):
    monkeypatch.setattr(system, "_clipboard_command", lambda: None)
    assert system.copy_to_clipboard("x") is False
