from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from snipmd import backends


class FakeBackend:
    """Stands in for GLM-OCR. Returns canned output per task prompt."""

    name = "fake"

    def __init__(self, outputs: dict[str, str] | None = None):
        self.outputs = outputs or {
            "Text Recognition:": "```markdown\n# Title\n\nEnergy is \\( E = mc^2 \\).\n```",
            "Formula Recognition:": "$$\n\\frac{a}{b}\n$$",
            "Table Recognition:": "<table><tr><td>x</td><td>y</td></tr>"
            "<tr><td>1</td><td>2</td></tr></table>",
        }
        self.calls: list[tuple[Path, str, int]] = []
        self.loaded = False

    def status(self) -> tuple[bool, str]:
        return True, "fake"

    def load(self) -> None:
        self.loaded = True

    def recognize(self, image: Path, prompt: str, max_tokens: int) -> str:
        assert image.exists()
        self.calls.append((image, prompt, max_tokens))
        return self.outputs[prompt]

    def is_downloaded(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def snip_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SNIPMD_HOME", str(home))
    return home


@pytest.fixture
def fake_backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(backends, "pick", lambda cfg, name=None: fake)
    return fake


@pytest.fixture
def image_file(tmp_path) -> Path:
    path = tmp_path / "eq.png"
    img = Image.new("RGB", (240, 60), "white")
    ImageDraw.Draw(img).text((10, 20), "a / b", fill="black")
    img.save(path)
    return path
