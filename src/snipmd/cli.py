"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

from snipmd import __version__, backends, config, history, system, vision
from snipmd.backends import BackendError
from snipmd.config import BACKENDS, MODES, Config, ConfigError
from snipmd.engine import Engine, InputError, Result

COMMANDS = ("app", "snip", "ocr", "serve", "history", "config", "doctor", "pull")

EPILOG = """examples:
  snipmd                        start the menu bar app (hotkey cmd+shift+2)
  snipmd snip --mode latex      drag a box, get LaTeX on the clipboard
  snipmd page.png               OCR a file to Markdown on stdout
  snipmd eq.png --mode latex --json
  snipmd serve                  local HTTP API on 127.0.0.1:8765
  snipmd doctor                 check backends, models and permissions
"""


def _err(msg: str) -> None:
    print(f"snipmd: {msg}", file=sys.stderr)


def _add_run_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("-m", "--mode", choices=MODES, help="output mode (default from config)")
    p.add_argument("-b", "--backend", choices=BACKENDS, help="OCR backend (default from config)")
    p.add_argument("--json", action="store_true", help="print a JSON object instead of text")
    p.add_argument("--preview", action="store_true", help="open the KaTeX preview page")
    p.add_argument("--no-history", action="store_true", help="do not record this result")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snipmd",
        description="Screenshot to Markdown, LaTeX or tables with a local OCR model.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"snipmd {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="log debug output")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("app", help="start the menu bar app (default when no command is given)")
    p.add_argument("-b", "--backend", choices=BACKENDS)

    p = sub.add_parser("snip", help="drag a box on screen, OCR it, copy the result")
    _add_run_options(p)
    p.add_argument("--no-copy", action="store_true", help="print only, leave the clipboard alone")

    p = sub.add_parser("ocr", help="OCR an image file (also: snipmd FILE)")
    p.add_argument("file", help="image path, or - to read image bytes from stdin")
    _add_run_options(p)
    p.add_argument("--copy", action="store_true", help="also copy the result to the clipboard")

    p = sub.add_parser("serve", help="run the local HTTP API for editor integrations")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, help="port (default from config, 8765)")
    p.add_argument("-b", "--backend", choices=BACKENDS)
    p.add_argument("--no-warm", action="store_true", help="load the model on first request")

    p = sub.add_parser("history", help="list, show or copy past snips")
    p.add_argument("-n", type=int, default=20, help="how many entries to list (default 20)")
    p.add_argument("--show", type=int, metavar="ID", help="print one entry in full")
    p.add_argument("--copy", type=int, metavar="ID", help="copy one entry to the clipboard")
    p.add_argument("--clear", action="store_true", help="delete all history and saved crops")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("config", help="show or change settings")
    p.add_argument(
        "action", nargs="?", default="show", choices=("show", "get", "set", "reset", "path")
    )
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("doctor", help="check backends, models and permissions")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("pull", help="download the OCR model ahead of the first snip")
    p.add_argument("-b", "--backend", choices=BACKENDS)
    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """`snipmd image.png ...` is shorthand for `snipmd ocr image.png ...`."""
    for i, arg in enumerate(argv):
        if arg in ("-v", "--verbose"):
            continue
        if arg.startswith("-") and arg != "-":
            return argv
        if arg in COMMANDS:
            return argv
        return [*argv[:i], "ocr", *argv[i:]]
    return argv


def _load_config() -> Config:
    try:
        return config.load()
    except ConfigError as exc:
        _err(str(exc))
        sys.exit(2)


def _emit(result: Result, as_json: bool, extra: dict | None = None) -> None:
    if as_json:
        payload = result.to_dict()
        payload.update(extra or {})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(result.text)


def _record(cfg: Config, result: Result, source: str, image: Path | None) -> int:
    entry = history.add(
        text=result.text,
        mode=result.mode,
        backend=result.backend,
        seconds=result.seconds,
        source=source,
        image=image,
        limit=cfg.history_limit,
        keep_image=cfg.keep_images,
    )
    return entry.id


def _run_engine(cfg: Config, args: argparse.Namespace, image: Path) -> Result | None:
    engine = Engine(cfg, args.backend)
    try:
        if engine.backend.name == "mlx" and not engine.backend.is_downloaded():  # type: ignore[attr-defined]
            _err(f"downloading {cfg.mlx_model} on first use, this takes a minute")
        return engine.run(image, args.mode)
    except InputError as exc:
        _err(str(exc))
    except BackendError as exc:
        _err(str(exc))
    return None


def cmd_ocr(cfg: Config, args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="snipmd-") as tmp:
        if args.file == "-":
            data = sys.stdin.buffer.read()
            if not data:
                _err("no image data on stdin")
                return 2
            image = Path(tmp) / "stdin.png"
            image.write_bytes(data)
        else:
            image = Path(args.file).expanduser()
            if not image.exists():
                _err(f"file not found: {image}")
                return 2
        result = _run_engine(cfg, args, image)
        if result is None:
            return 1
        extra: dict = {"source": str(args.file)}
        if not args.no_history:
            extra["id"] = _record(cfg, result, "file", image)
    if args.copy:
        extra["copied"] = system.copy_to_clipboard(result.text)
        if not extra["copied"]:
            _err("no clipboard tool found (pbcopy, wl-copy, xclip or xsel)")
    _emit(result, args.json, extra)
    if not result.text:
        _err("no text found in the image")
    if args.preview or cfg.preview:
        system_page = _preview(result)
        if system_page and not args.json:
            _err(f"preview: {system_page}")
    return 0


def cmd_snip(cfg: Config, args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="snipmd-") as tmp:
        try:
            shot = system.capture_region(Path(tmp) / "snip.png")
        except system.CaptureError as exc:
            _err(str(exc))
            return 1
        if shot is None:
            _err("cancelled")
            return 130
        result = _run_engine(cfg, args, shot)
        if result is None:
            return 1
        extra: dict = {"source": "screen"}
        if not args.no_history:
            extra["id"] = _record(cfg, result, "snip", shot)
    if not args.no_copy and result.text:
        extra["copied"] = system.copy_to_clipboard(result.text)
    _emit(result, args.json, extra)
    if not result.text:
        _err("no text found in the selection")
    elif extra.get("copied"):
        _err(f"copied {result.mode} to the clipboard ({result.seconds:.2f} s, {result.backend})")
    if args.preview or cfg.preview:
        _preview(result)
    return 0


def _preview(result: Result) -> Path | None:
    from snipmd import preview

    try:
        return preview.show(result.text, result.mode, result.backend, result.seconds)
    except OSError as exc:
        _err(f"could not open the preview: {exc}")
        return None


def cmd_serve(cfg: Config, args: argparse.Namespace) -> int:
    from snipmd.server import make_server

    engine = Engine(cfg, args.backend)
    if not args.no_warm:
        try:
            name = engine.warm()
            print(f"backend: {name}", file=sys.stderr)
        except BackendError as exc:
            _err(str(exc))
            return 1
    port = args.port or cfg.port
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        _err(f"warning: binding to {args.host} exposes the API to your network")
    try:
        server = make_server(engine, args.host, port)
    except OSError as exc:
        _err(f"cannot listen on {args.host}:{port}: {exc}")
        return 1
    print(f"snipmd API on http://{args.host}:{port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_history(cfg: Config, args: argparse.Namespace) -> int:
    if args.clear:
        n = history.clear()
        print(f"deleted {n} entries")
        return 0
    if args.show is not None or args.copy is not None:
        entry_id = args.show if args.show is not None else args.copy
        entry = history.get(entry_id)
        if entry is None:
            _err(f"no history entry with id {entry_id}")
            return 1
        if args.copy is not None:
            if not system.copy_to_clipboard(entry.text):
                _err("no clipboard tool found")
                return 1
            _err(f"copied entry {entry.id}")
            return 0
        if args.json:
            print(json.dumps(entry.__dict__, ensure_ascii=False, indent=2))
        else:
            print(entry.text)
        return 0
    entries = history.recent(args.n)
    if args.json:
        print(json.dumps([e.__dict__ for e in entries], ensure_ascii=False, indent=2))
        return 0
    if not entries:
        print("No snips yet. Press the hotkey in the menu bar app or run `snipmd snip`.")
        return 0
    for e in entries:
        first = e.text.strip().splitlines()[0] if e.text.strip() else "(empty)"
        if len(first) > 70:
            first = first[:67] + "..."
        print(f"{e.id:>4}  {e.time.replace('T', ' ')}  {e.mode:<8}  {first}")
    return 0


def cmd_config(cfg: Config, args: argparse.Namespace) -> int:
    path = config.config_path()
    if args.action == "path":
        print(path)
        return 0
    if args.action == "reset":
        config.save(Config(), path)
        print(f"reset {path}")
        return 0
    if args.action == "get":
        if not args.key:
            _err("usage: snipmd config get KEY")
            return 2
        if args.key not in Config.field_names():
            _err(f"unknown key '{args.key}'. Valid keys: {', '.join(Config.field_names())}")
            return 2
        value = getattr(cfg, args.key)
        print(json.dumps(value) if args.json else value)
        return 0
    if args.action == "set":
        if not args.key or args.value is None:
            _err("usage: snipmd config set KEY VALUE")
            return 2
        try:
            setattr(cfg, args.key, config.coerce(args.key, args.value))
        except (ConfigError, ValueError) as exc:
            _err(str(exc))
            return 2
        config.save(cfg, path)
        print(f"{args.key} = {getattr(cfg, args.key)}")
        return 0
    if args.json:
        print(json.dumps(cfg.to_dict(), indent=2))
        return 0
    print(f"# {path}{'' if path.exists() else ' (not created yet, showing defaults)'}")
    for key, value in cfg.to_dict().items():
        print(f"{key} = {json.dumps(value)}")
    return 0


def doctor_report(cfg: Config) -> dict:
    report: dict = {"version": __version__, "platform": sys.platform, "checks": []}

    def check(name: str, ok: bool, detail: str) -> None:
        report["checks"].append({"name": name, "ok": ok, "detail": detail})

    for name in ("mlx", "ollama"):
        try:
            ok, detail = backends.make(name, cfg).status()
        except BackendError as exc:
            ok, detail = False, str(exc)
        check(f"backend {name}", ok, detail)
    try:
        chosen = backends.pick(cfg)
        check("backend auto", True, f"auto picks {chosen.name}")
    except BackendError as exc:
        check("backend auto", False, str(exc).splitlines()[0])
    check(
        "apple vision",
        vision.available(),
        "fast path for text mode" if vision.available() else "not available on this system",
    )
    import shutil as _sh

    has_capture = _sh.which("screencapture") is not None
    check(
        "region capture",
        has_capture,
        "screencapture found" if has_capture else "macOS only, use snipmd FILE",
    )
    clip = system._clipboard_command()
    check("clipboard", clip is not None, " ".join(clip) if clip else "no clipboard tool found")
    report["ready"] = any(c["ok"] for c in report["checks"] if c["name"] == "backend auto")
    return report


def cmd_doctor(cfg: Config, args: argparse.Namespace) -> int:
    report = doctor_report(cfg)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for c in report["checks"]:
            print(f"{'ok  ' if c['ok'] else 'no  '} {c['name']:<16} {c['detail']}")
        print(f"\nconfig: {config.config_path()}")
        if sys.platform == "darwin":
            print(
                "permissions: the menu bar hotkey needs Input Monitoring, the capture needs "
                "Screen Recording.\nGrant both to your terminal or Python in System Settings, "
                "Privacy and Security."
            )
    return 0 if report["ready"] else 1


def cmd_pull(cfg: Config, args: argparse.Namespace) -> int:
    name = args.backend or cfg.backend
    if name == "auto":
        name = "mlx" if backends.is_apple_silicon() else "ollama"
    try:
        backend = backends.make(name, cfg)
        if name == "mlx":
            if not backend.can_download():  # type: ignore[attr-defined]
                _err("the mlx backend needs Apple Silicon with mlx-vlm installed")
                return 1
            print(f"downloading {cfg.mlx_model} from Hugging Face", file=sys.stderr)
            path = backend.pull()  # type: ignore[attr-defined]
            print(f"ready: {path}")
        else:
            print(f"pulling {cfg.ollama_model} through Ollama", file=sys.stderr)
            backend.installed_models()  # type: ignore[attr-defined]
            backend.pull()  # type: ignore[attr-defined]
            print(f"ready: {cfg.ollama_model}")
    except BackendError as exc:
        _err(str(exc))
        return 1
    return 0


def cmd_app(cfg: Config, args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        _err("the menu bar app runs on macOS only. Use `snipmd FILE` or `snipmd serve`.")
        return 1
    try:
        from snipmd.app import run
    except ImportError as exc:
        _err(f"menu bar dependencies are missing ({exc}). Reinstall snipmd on macOS.")
        return 1
    return run(cfg, getattr(args, "backend", None))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(_normalize_argv(argv))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = _load_config()
    command = args.command or "app"
    handlers = {
        "app": cmd_app,
        "snip": cmd_snip,
        "ocr": cmd_ocr,
        "serve": cmd_serve,
        "history": cmd_history,
        "config": cmd_config,
        "doctor": cmd_doctor,
        "pull": cmd_pull,
    }
    try:
        return handlers[command](cfg, args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
