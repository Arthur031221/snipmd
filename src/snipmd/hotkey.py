"""Hotkey strings.

Users write ``cmd+shift+2``. pynput wants ``<cmd>+<shift>+2``. This module
converts between the two and validates the input.
"""

from __future__ import annotations

MODIFIERS = {
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "shift": "shift",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "opt": "alt",
    "option": "alt",
}

NAMED_KEYS = {
    "space",
    "tab",
    "enter",
    "esc",
    "f1",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f11",
    "f12",
}


class HotkeyError(ValueError):
    pass


def parse_hotkey(text: str) -> tuple[list[str], str]:
    """Split a hotkey into sorted modifiers and one main key."""
    parts = [p.strip().lower().strip("<>") for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise HotkeyError("empty hotkey")
    mods: list[str] = []
    keys: list[str] = []
    for part in parts:
        if part in MODIFIERS:
            mod = MODIFIERS[part]
            if mod not in mods:
                mods.append(mod)
        else:
            keys.append(part)
    if len(keys) != 1:
        raise HotkeyError(f"hotkey needs exactly one non-modifier key, got '{text}'")
    key = keys[0]
    if len(key) != 1 and key not in NAMED_KEYS:
        raise HotkeyError(f"unknown key '{key}' in hotkey '{text}'")
    if not mods:
        raise HotkeyError(f"hotkey needs at least one modifier (cmd, ctrl, alt, shift): '{text}'")
    order = ["ctrl", "alt", "shift", "cmd"]
    mods.sort(key=order.index)
    return mods, key


def to_pynput(text: str) -> str:
    mods, key = parse_hotkey(text)
    main = f"<{key}>" if key in NAMED_KEYS else key
    return "+".join([f"<{m}>" for m in mods] + [main])


def pretty(text: str) -> str:
    mods, key = parse_hotkey(text)
    return "+".join([*mods, key])
