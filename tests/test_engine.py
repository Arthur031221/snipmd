import pytest
from PIL import Image

from snipmd import engine, vision
from snipmd.config import Config
from snipmd.engine import Engine, InputError, prepare_image


def test_prepare_pads_and_upscales_small_crop(tmp_path, image_file):
    out = prepare_image(image_file, tmp_path)
    img = Image.open(out)
    # 240 px wide is below MIN_SIDE, so it is scaled by 2, then padded.
    assert img.width > 480
    assert img.getpixel((0, 0)) == (255, 255, 255)


def test_prepare_flattens_transparency(tmp_path):
    src = tmp_path / "t.png"
    Image.new("RGBA", (600, 200), (0, 0, 0, 0)).save(src)
    out = Image.open(prepare_image(src, tmp_path))
    assert out.mode == "RGB"
    assert out.getpixel((300, 100)) == (255, 255, 255)


def test_prepare_shrinks_huge_image(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (6000, 1000), "white").save(src)
    out = Image.open(prepare_image(src, tmp_path))
    assert max(out.size) <= engine.MAX_SIDE + 2 * 200


def test_prepare_rejects_non_images(tmp_path):
    bad = tmp_path / "x.png"
    bad.write_text("not an image")
    with pytest.raises(InputError):
        prepare_image(bad, tmp_path)
    with pytest.raises(InputError):
        prepare_image(tmp_path / "missing.png", tmp_path)


def test_prepare_rejects_tiny(tmp_path):
    src = tmp_path / "tiny.png"
    Image.new("RGB", (2, 2), "white").save(src)
    with pytest.raises(InputError):
        prepare_image(src, tmp_path)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("markdown", "# Title\n\nEnergy is $E = mc^2$."),
        ("latex", "\\frac{a}{b}"),
        ("table", "| x | y |\n| --- | --- |\n| 1 | 2 |"),
    ],
)
def test_run_modes(fake_backend, image_file, mode, expected):
    result = Engine(Config()).run(image_file, mode)
    assert result.text == expected
    assert result.mode == mode
    assert result.backend == "fake"
    assert result.seconds >= 0


def test_run_uses_config_mode_and_max_tokens(fake_backend, image_file):
    cfg = Config(mode="latex", max_tokens=77)
    Engine(cfg).run(image_file)
    assert fake_backend.calls[-1][1] == "Formula Recognition:"
    assert fake_backend.calls[-1][2] == 77


def test_text_mode_uses_vision_when_available(fake_backend, image_file, monkeypatch):
    monkeypatch.setattr(vision, "available", lambda: True)
    monkeypatch.setattr(vision, "recognize", lambda path: "hello   world\n\n\n\nbye")
    result = Engine(Config(text_engine="vision")).run(image_file, "text")
    assert result.backend == "vision"
    assert result.text == "hello world\n\nbye"
    assert fake_backend.calls == []


def test_text_mode_model_engine(fake_backend, image_file, monkeypatch):
    monkeypatch.setattr(vision, "available", lambda: True)
    result = Engine(Config(text_engine="model")).run(image_file, "text")
    assert result.backend == "fake"
    assert result.text == "Title\n\nEnergy is $E = mc^2$."


def test_text_mode_vision_failure_falls_back(fake_backend, image_file, monkeypatch):
    def boom(path):
        raise vision.VisionUnavailable("no")

    monkeypatch.setattr(vision, "available", lambda: True)
    monkeypatch.setattr(vision, "recognize", boom)
    assert Engine(Config()).run(image_file, "text").backend == "fake"


def test_unknown_mode(fake_backend, image_file):
    with pytest.raises(InputError):
        Engine(Config()).run(image_file, "html")


def test_warm_loads_backend(fake_backend):
    assert Engine(Config()).warm() == "fake"
    assert fake_backend.loaded


def test_vision_line_grouping():
    items = [
        (0.50, 0.6, 0.1, "world"),
        (0.10, 0.0, 0.1, "Title"),
        (0.52, 0.1, 0.1, "hello"),
    ]
    assert vision._group_lines(items) == ["Title", "hello world"]
