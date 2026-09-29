import json
import shutil

import pytest

from snipmd import cli, history, system


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_normalize_argv():
    assert cli._normalize_argv(["img.png", "--mode", "latex"]) == [
        "ocr",
        "img.png",
        "--mode",
        "latex",
    ]
    assert cli._normalize_argv(["-v", "img.png"]) == ["-v", "ocr", "img.png"]
    assert cli._normalize_argv(["history"]) == ["history"]
    assert cli._normalize_argv(["--version"]) == ["--version"]
    assert cli._normalize_argv(["-"]) == ["ocr", "-"]
    assert cli._normalize_argv([]) == []


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "snipmd 0.1.0" in capsys.readouterr().out


def test_help_for_every_command(capsys):
    for command in cli.COMMANDS:
        with pytest.raises(SystemExit) as exc:
            cli.main([command, "--help"])
        assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out


def test_ocr_file_latex(capsys, fake_backend, image_file):
    code, out, _ = run(capsys, str(image_file), "--mode", "latex")
    assert code == 0
    assert out.strip() == "\\frac{a}{b}"
    assert history.recent(1)[0].text == "\\frac{a}{b}"


def test_ocr_json(capsys, fake_backend, image_file):
    code, out, _ = run(capsys, "ocr", str(image_file), "--mode", "table", "--json", "--no-history")
    data = json.loads(out)
    assert code == 0
    assert data["mode"] == "table"
    assert data["text"].startswith("| x | y |")
    assert "id" not in data
    assert history.load() == []


def test_ocr_stdin(capsys, fake_backend, image_file, monkeypatch):
    class Stdin:
        buffer = open(image_file, "rb")  # noqa: SIM115

    monkeypatch.setattr("sys.stdin", Stdin)
    code, out, _ = run(capsys, "-", "--mode", "latex")
    Stdin.buffer.close()
    assert code == 0 and out.strip() == "\\frac{a}{b}"


def test_ocr_missing_file(capsys, fake_backend):
    code, _, err = run(capsys, "nope.png")
    assert code == 2
    assert "file not found" in err


def test_ocr_copy(capsys, fake_backend, image_file, monkeypatch):
    copied = []
    monkeypatch.setattr(system, "copy_to_clipboard", lambda t: copied.append(t) or True)
    code, out, _ = run(capsys, str(image_file), "--mode", "latex", "--copy", "--json")
    assert code == 0
    assert copied == ["\\frac{a}{b}"]
    assert json.loads(out)["copied"] is True


def test_ocr_backend_error(capsys, image_file, monkeypatch):
    from snipmd import backends

    def fail(cfg, name=None):
        raise backends.BackendUnavailable("no OCR backend is ready.")

    monkeypatch.setattr(backends, "pick", fail)
    code, _, err = run(capsys, str(image_file))
    assert code == 1
    assert "no OCR backend is ready" in err


def test_snip_copies_result(capsys, fake_backend, image_file, monkeypatch):
    def fake_capture(dest, timeout=300):
        shutil.copyfile(image_file, dest)
        return dest

    copied = []
    monkeypatch.setattr(system, "capture_region", fake_capture)
    monkeypatch.setattr(system, "copy_to_clipboard", lambda t: copied.append(t) or True)
    code, _, err = run(capsys, "snip", "--mode", "latex")
    assert code == 0
    assert copied == ["\\frac{a}{b}"]
    assert "copied latex" in err
    entry = history.recent(1)[0]
    assert entry.source == "snip" and entry.image


def test_snip_cancelled(capsys, fake_backend, monkeypatch):
    monkeypatch.setattr(system, "capture_region", lambda dest, timeout=300: None)
    code, _, err = run(capsys, "snip")
    assert code == 130
    assert "cancelled" in err


def test_snip_capture_error(capsys, fake_backend, monkeypatch):
    def fail(dest, timeout=300):
        raise system.CaptureError("macOS only")

    monkeypatch.setattr(system, "capture_region", fail)
    code, _, err = run(capsys, "snip")
    assert code == 1 and "macOS only" in err


def test_history_commands(capsys, fake_backend, image_file, monkeypatch):
    code, out, _ = run(capsys, "history")
    assert code == 0 and "No snips yet" in out
    run(capsys, str(image_file), "--mode", "latex")
    code, out, _ = run(capsys, "history")
    assert "latex" in out and "\\frac{a}{b}" in out
    code, out, _ = run(capsys, "history", "--json")
    assert json.loads(out)[0]["id"] == 1
    code, out, _ = run(capsys, "history", "--show", "1")
    assert out.strip() == "\\frac{a}{b}"
    copied = []
    monkeypatch.setattr(system, "copy_to_clipboard", lambda t: copied.append(t) or True)
    assert run(capsys, "history", "--copy", "1")[0] == 0
    assert copied == ["\\frac{a}{b}"]
    assert run(capsys, "history", "--show", "99")[0] == 1
    code, out, _ = run(capsys, "history", "--clear")
    assert "deleted 1" in out


def test_config_commands(capsys, snip_home):
    code, out, _ = run(capsys, "config")
    assert code == 0 and 'mode = "markdown"' in out
    code, out, _ = run(capsys, "config", "set", "mode", "latex")
    assert code == 0 and "mode = latex" in out
    code, out, _ = run(capsys, "config", "get", "mode")
    assert out.strip() == "latex"
    code, out, _ = run(capsys, "config", "--json")
    assert json.loads(out)["mode"] == "latex"
    code, _, err = run(capsys, "config", "set", "mode", "html")
    assert code == 2 and "must be one of" in err
    code, _, err = run(capsys, "config", "set", "hotkey", "shift")
    assert code == 2
    code, out, _ = run(capsys, "config", "path")
    assert out.strip() == str(snip_home / "config.toml")
    run(capsys, "config", "reset")
    assert run(capsys, "config", "get", "mode")[1].strip() == "markdown"
    assert run(capsys, "config", "get", "bogus")[0] == 2


def test_broken_config_exits_cleanly(capsys, snip_home):
    snip_home.mkdir(parents=True)
    (snip_home / "config.toml").write_text("mode = 'html'\n")
    with pytest.raises(SystemExit) as exc:
        cli.main(["history"])
    assert exc.value.code == 2
    assert "must be one of" in capsys.readouterr().err


def test_doctor_json(capsys, monkeypatch):
    from snipmd import backends

    class Ready:
        name = "ollama"

        def status(self):
            return True, "ok"

    monkeypatch.setattr(backends, "make", lambda name, cfg: Ready())
    monkeypatch.setattr(backends, "pick", lambda cfg, name=None: Ready())
    code, out, _ = run(capsys, "doctor", "--json")
    report = json.loads(out)
    assert code == 0 and report["ready"] is True
    names = [c["name"] for c in report["checks"]]
    assert "backend auto" in names and "clipboard" in names


def test_doctor_nothing_ready(capsys, monkeypatch):
    from snipmd import backends

    class Down:
        name = "ollama"

        def status(self):
            return False, "down"

    def fail(cfg, name=None):
        raise backends.BackendUnavailable("no OCR backend is ready.\n  details")

    monkeypatch.setattr(backends, "make", lambda name, cfg: Down())
    monkeypatch.setattr(backends, "pick", fail)
    code, out, _ = run(capsys, "doctor")
    assert code == 1
    assert "no OCR backend is ready" in out


def test_app_off_macos(capsys, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    code, _, err = run(capsys, "app")
    assert code == 1 and "macOS only" in err
