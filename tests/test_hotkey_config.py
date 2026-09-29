import pytest

from snipmd import config
from snipmd.config import Config, ConfigError
from snipmd.hotkey import HotkeyError, parse_hotkey, pretty, to_pynput


def test_hotkey_conversion():
    assert to_pynput("cmd+shift+2") == "<shift>+<cmd>+2"
    assert to_pynput("Command + Option + L") == "<alt>+<cmd>+l"
    assert to_pynput("<ctrl>+<alt>+<space>") == "<ctrl>+<alt>+<space>"
    assert pretty("shift+cmd+2") == "shift+cmd+2"


@pytest.mark.parametrize("bad", ["", "2", "cmd+shift", "cmd+a+b", "cmd+enterx"])
def test_hotkey_errors(bad):
    with pytest.raises(HotkeyError):
        parse_hotkey(bad)


def test_home_override(snip_home):
    assert config.home() == snip_home
    assert config.config_path() == snip_home / "config.toml"


def test_defaults_when_missing():
    cfg = config.load()
    assert cfg.mode == "markdown"
    assert cfg.hotkey == "cmd+shift+2"
    assert cfg.backend == "auto"


def test_save_load_roundtrip():
    cfg = Config(mode="latex", port=9000, notify=False, ollama_model='we"ird')
    path = config.save(cfg)
    assert path.exists()
    again = config.load()
    assert again == cfg


def test_unknown_keys_are_ignored(snip_home):
    snip_home.mkdir(parents=True)
    (snip_home / "config.toml").write_text('mode = "table"\nfuture_key = 1\n')
    assert config.load().mode == "table"


def test_bad_toml(snip_home):
    snip_home.mkdir(parents=True)
    (snip_home / "config.toml").write_text("mode = \n")
    with pytest.raises(ConfigError):
        config.load()


@pytest.mark.parametrize(
    "key,raw,expected",
    [
        ("mode", "latex", "latex"),
        ("notify", "off", False),
        ("preview", "yes", True),
        ("port", "9001", 9001),
        ("hotkey", "ctrl+alt+m", "ctrl+alt+m"),
    ],
)
def test_coerce(key, raw, expected):
    assert config.coerce(key, raw) == expected


@pytest.mark.parametrize(
    "key,raw",
    [("mode", "html"), ("port", "abc"), ("port", "-1"), ("notify", "maybe"), ("nope", "1")],
)
def test_coerce_errors(key, raw):
    with pytest.raises(ConfigError):
        config.coerce(key, raw)


def test_coerce_bad_hotkey():
    with pytest.raises(ValueError):
        config.coerce("hotkey", "shift")
