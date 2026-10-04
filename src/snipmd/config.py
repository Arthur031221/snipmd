"""Settings stored as a flat TOML file.

The file lives in the snipmd home directory, which is
``~/Library/Application Support/snipmd`` on macOS, ``$XDG_CONFIG_HOME/snipmd``
elsewhere, or whatever ``SNIPMD_HOME`` points to.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

MODES = ("markdown", "latex", "table", "text")
BACKENDS = ("auto", "mlx", "ollama")
TEXT_ENGINES = ("vision", "model")
TABLE_FORMATS = ("markdown", "csv")


def home() -> Path:
    env = os.environ.get("SNIPMD_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "snipmd"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "snipmd"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "snipmd"


def config_path() -> Path:
    return home() / "config.toml"


@dataclass
class Config:
    mode: str = "markdown"
    backend: str = "auto"
    hotkey: str = "cmd+shift+2"
    text_engine: str = "vision"
    table_format: str = "markdown"
    mlx_model: str = "mlx-community/GLM-OCR-8bit"
    ollama_model: str = "glm-ocr:q8_0"
    ollama_url: str = "http://localhost:11434"
    max_tokens: int = 2048
    port: int = 8765
    notify: bool = True
    preview: bool = False
    history_limit: int = 500
    keep_images: bool = True

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def to_dict(self) -> dict:
        return asdict(self)


class ConfigError(ValueError):
    pass


_CHOICES = {
    "mode": MODES,
    "backend": BACKENDS,
    "text_engine": TEXT_ENGINES,
    "table_format": TABLE_FORMATS,
}


def coerce(key: str, raw: object) -> object:
    """Convert a raw value (usually a CLI string) to the type of ``key``."""
    if key not in Config.field_names():
        valid = ", ".join(Config.field_names())
        raise ConfigError(f"unknown key '{key}'. Valid keys: {valid}")
    default = getattr(Config(), key)
    if isinstance(default, bool):
        if isinstance(raw, bool):
            value: object = raw
        elif str(raw).lower() in ("1", "true", "yes", "on"):
            value = True
        elif str(raw).lower() in ("0", "false", "no", "off"):
            value = False
        else:
            raise ConfigError(f"{key} must be true or false, got '{raw}'")
    elif isinstance(default, int):
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{key} must be an integer, got '{raw}'") from exc
        if value < 0:
            raise ConfigError(f"{key} must not be negative")
    else:
        value = str(raw).strip()
    if key in _CHOICES and value not in _CHOICES[key]:
        raise ConfigError(f"{key} must be one of {', '.join(_CHOICES[key])}, got '{value}'")
    if key == "hotkey":
        from snipmd.hotkey import parse_hotkey

        parse_hotkey(str(value))
    return value


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if not path.exists():
        return cfg
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"cannot parse {path}: {exc}") from exc
    for key, raw in data.items():
        if key not in Config.field_names():
            continue
        setattr(cfg, key, coerce(key, raw))
    return cfg


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def save(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# snipmd settings. Edit here or with `snipmd config set KEY VALUE`."]
    lines += [f"{k} = {_toml_value(v)}" for k, v in cfg.to_dict().items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
