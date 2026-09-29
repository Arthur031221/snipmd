"""Thin wrappers around OS tools: region capture, clipboard, notifications."""

from __future__ import annotations

import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


class CaptureError(RuntimeError):
    pass


def capture_region(dest: Path, timeout: float = 300) -> Path | None:
    """Show the macOS crosshair and save the selected region to ``dest``.

    Returns None when the user presses Escape. Uses the built-in
    ``screencapture -i -x`` so there is no custom overlay window to maintain.
    """
    tool = shutil.which("screencapture")
    if tool is None:
        raise CaptureError(
            "region capture needs macOS (screencapture was not found). "
            "Pass an image file instead: snipmd image.png"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        proc = subprocess.run(
            [tool, "-i", "-x", str(dest)], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None
    if not dest.exists() or dest.stat().st_size == 0:
        err = (proc.stderr or "").strip()
        if "could not create image" in err:
            raise CaptureError(
                "macOS refused the capture. Grant Screen Recording to your terminal "
                "(System Settings, Privacy and Security, Screen Recording) and retry."
            )
        return None
    return dest


def _clipboard_command() -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        return ["pbcopy"]
    if sys.platform == "win32":
        return ["clip"]
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "-i"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def copy_to_clipboard(text: str) -> bool:
    cmd = _clipboard_command()
    if cmd is None:
        return False
    env = None
    if cmd[0] == "pbcopy":
        # pbcopy picks the encoding from the locale. Force UTF-8 so Greek
        # letters and math symbols survive.
        import os

        env = {**os.environ, "LANG": "en_US.UTF-8", "LC_CTYPE": "UTF-8"}
    try:
        subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _osa_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title: str, message: str) -> bool:
    """Show a system notification. Returns False when there is no way to."""
    message = message if len(message) <= 180 else message[:177] + "..."
    if sys.platform == "darwin" and shutil.which("osascript"):
        script = f"display notification {_osa_quote(message)} with title {_osa_quote(title)}"
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return False
        return True
    if shutil.which("notify-send"):
        try:
            subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return False
        return True
    return False


def open_path(path: Path) -> None:
    if sys.platform == "darwin" and shutil.which("open"):
        subprocess.run(["open", str(path)], check=False)
    else:
        webbrowser.open(path.as_uri())
