"""Menu bar app: global hotkey, crosshair capture, OCR, clipboard, notification.

AppKit is not thread safe, so every UI change goes through a queue that a
rumps timer drains on the main thread. Capture and OCR run on a worker
thread, one snip at a time.
"""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
from importlib import resources
from pathlib import Path

import rumps

from snipmd import config, history, system
from snipmd.backends import BackendError
from snipmd.config import Config
from snipmd.engine import Engine, InputError
from snipmd.hotkey import HotkeyError, pretty, to_pynput

log = logging.getLogger("snipmd")

MODE_LABELS = {"markdown": "Markdown", "latex": "LaTeX", "table": "Table", "text": "Plain text"}
RECENT_COUNT = 8


def _has_bundle_id() -> bool:
    try:
        from Foundation import NSBundle

        return NSBundle.mainBundle().bundleIdentifier() is not None
    except ImportError:
        return False


def _input_trusted() -> bool:
    """True when macOS lets this process watch global key events.

    Passing the prompt option makes macOS show its permission dialog the
    first time, which is friendlier than a silent dead hotkey.
    """
    try:
        import HIServices
    except ImportError:
        return True
    try:
        options = {HIServices.kAXTrustedCheckOptionPrompt: True}
        return bool(HIServices.AXIsProcessTrustedWithOptions(options))
    except AttributeError:
        return bool(HIServices.AXIsProcessTrusted())


class SnipApp(rumps.App):
    def __init__(self, cfg: Config, backend: str | None = None):
        icon = resources.files("snipmd").joinpath("assets", "icon.png")
        super().__init__("snipmd", icon=str(icon), template=True, quit_button=None)
        self.cfg = cfg
        self.engine = Engine(cfg, backend)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.busy = threading.Lock()
        self.listener = None
        self.use_rumps_notify = _has_bundle_id()

        self.snip_item = rumps.MenuItem(f"Snip    {pretty(cfg.hotkey)}", callback=self.on_snip)
        self.status_item = rumps.MenuItem("Loading model...")
        self.mode_items = {
            mode: rumps.MenuItem(label, callback=self.on_mode)
            for mode, label in MODE_LABELS.items()
        }
        self.recent_menu = rumps.MenuItem("Recent")
        self.preview_item = rumps.MenuItem("Open preview after each snip", callback=self.on_preview)
        self.menu = [
            self.snip_item,
            self.status_item,
            None,
            *self.mode_items.values(),
            None,
            self.recent_menu,
            self.preview_item,
            rumps.MenuItem("Settings...", callback=self.on_settings),
            rumps.MenuItem("Show history folder", callback=self.on_history_folder),
            None,
            rumps.MenuItem("Quit snipmd", callback=self.on_quit),
        ]
        self._sync_mode_marks()
        self.preview_item.state = int(cfg.preview)
        self._refresh_recent()

        self.timer = rumps.Timer(self._drain, 0.15)
        self.timer.start()
        threading.Thread(target=self._warm, daemon=True).start()
        self._start_hotkey()

    # UI helpers, main thread only.

    def _sync_mode_marks(self) -> None:
        for mode, item in self.mode_items.items():
            item.state = int(mode == self.cfg.mode)

    def _refresh_recent(self) -> None:
        if self.recent_menu._menu is not None:
            self.recent_menu.clear()
        entries = history.recent(RECENT_COUNT)
        if not entries:
            self.recent_menu.add(rumps.MenuItem("No snips yet"))
            return
        for entry in entries:
            label = entry.text.strip().splitlines()[0] if entry.text.strip() else "(empty)"
            label = label if len(label) <= 48 else label[:45] + "..."
            item = rumps.MenuItem(f"{MODE_LABELS.get(entry.mode, entry.mode)}: {label}")
            item.set_callback(lambda _sender, text=entry.text: self._copy(text))
            self.recent_menu.add(item)

    def _notify(self, title: str, message: str) -> None:
        if not self.cfg.notify:
            return
        if self.use_rumps_notify:
            rumps.notification(title, "", message, sound=False)
        else:
            threading.Thread(target=system.notify, args=(title, message), daemon=True).start()

    def _copy(self, text: str) -> None:
        if system.copy_to_clipboard(text):
            self._notify("snipmd", "Copied from history")

    def _drain(self, _timer) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            kind = event[0]
            if kind == "status":
                self.status_item.title = event[1]
            elif kind == "busy":
                self.title = "..." if event[1] else None
            elif kind == "done":
                result, copied = event[1], event[2]
                self.title = None
                self._refresh_recent()
                if not result.text:
                    self._notify("snipmd", "No text found in the selection")
                    continue
                head = f"{MODE_LABELS[result.mode]} copied" if copied else "Clipboard failed"
                self._notify(f"{head} in {result.seconds:.1f} s", result.text)
                if self.cfg.preview:
                    from snipmd import preview

                    preview.show(result.text, result.mode, result.backend, result.seconds)
            elif kind == "error":
                self.title = None
                self._notify("snipmd error", event[1])

    # Worker side.

    def _warm(self) -> None:
        try:
            name = self.engine.warm()
            self.events.put(("status", f"Ready ({name}, {MODE_LABELS[self.cfg.mode]})"))
        except BackendError as exc:
            first = str(exc).splitlines()[0]
            self.events.put(("status", "No OCR backend, run `snipmd doctor`"))
            self.events.put(("error", first))

    def _start_hotkey(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            self.events.put(("error", "pynput is missing, the hotkey is off. Use the menu."))
            return
        try:
            combo = to_pynput(self.cfg.hotkey)
        except HotkeyError as exc:
            self.events.put(("error", f"bad hotkey in settings: {exc}"))
            return
        self.listener = keyboard.GlobalHotKeys({combo: self._on_hotkey})
        self.listener.daemon = True
        self.listener.start()
        if not _input_trusted():
            self.events.put(
                (
                    "error",
                    "The hotkey needs Accessibility or Input Monitoring permission for this "
                    "terminal. Grant it, then restart snipmd. The Snip menu item works now.",
                )
            )

    def _on_hotkey(self) -> None:
        self.start_snip()

    def start_snip(self) -> None:
        if not self.busy.acquire(blocking=False):
            return
        threading.Thread(target=self._snip_worker, daemon=True).start()

    def _snip_worker(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="snipmd-") as tmp:
                try:
                    shot = system.capture_region(Path(tmp) / "snip.png")
                except system.CaptureError as exc:
                    self.events.put(("error", str(exc)))
                    return
                if shot is None:
                    return
                self.events.put(("busy", True))
                try:
                    result = self.engine.run(shot, self.cfg.mode)
                except (InputError, BackendError) as exc:
                    self.events.put(("error", str(exc).splitlines()[0]))
                    return
                copied = bool(result.text) and system.copy_to_clipboard(result.text)
                history.add(
                    text=result.text,
                    mode=result.mode,
                    backend=result.backend,
                    seconds=result.seconds,
                    source="hotkey",
                    image=shot,
                    limit=self.cfg.history_limit,
                    keep_image=self.cfg.keep_images,
                )
                self.events.put(("done", result, copied))
        except Exception as exc:  # keep the app alive whatever happens in one snip
            log.exception("snip failed")
            self.events.put(("error", f"snip failed: {exc}"))
        finally:
            self.events.put(("busy", False))
            self.busy.release()

    # Menu callbacks.

    def on_snip(self, _sender) -> None:
        self.start_snip()

    def on_mode(self, sender) -> None:
        mode = next(m for m, label in MODE_LABELS.items() if label == sender.title)
        self.cfg.mode = mode
        config.save(self.cfg)
        self._sync_mode_marks()
        name = self.engine._backend.name if self.engine._backend else "loading"
        self.status_item.title = f"Ready ({name}, {MODE_LABELS[mode]})"

    def on_preview(self, sender) -> None:
        self.cfg.preview = not self.cfg.preview
        sender.state = int(self.cfg.preview)
        config.save(self.cfg)

    def on_settings(self, _sender) -> None:
        path = config.config_path()
        if not path.exists():
            config.save(self.cfg, path)
        system.open_path(path)

    def on_history_folder(self, _sender) -> None:
        folder = config.home()
        folder.mkdir(parents=True, exist_ok=True)
        system.open_path(folder)

    def on_quit(self, _sender) -> None:
        if self.listener is not None:
            self.listener.stop()
        rumps.quit_application()


def run(cfg: Config, backend: str | None = None) -> int:
    print(
        f"snipmd is in the menu bar. Press {pretty(cfg.hotkey)} to snip. "
        "Quit from the menu or with Ctrl+C.",
        flush=True,
    )
    SnipApp(cfg, backend).run()
    return 0
