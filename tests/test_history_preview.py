import json

from snipmd import history, preview


def _add(text, image=None, limit=500, keep=True):
    return history.add(
        text=text,
        mode="latex",
        backend="fake",
        seconds=0.5,
        source="test",
        image=image,
        limit=limit,
        keep_image=keep,
    )


def test_empty_history():
    assert history.load() == []
    assert history.recent() == []
    assert history.get(1) is None


def test_add_and_recent_order():
    _add("one")
    _add("two")
    assert [e.text for e in history.recent()] == ["two", "one"]
    assert [e.id for e in history.load()] == [1, 2]
    assert history.get(2).text == "two"


def test_image_is_kept_and_trimmed(image_file):
    first = _add("a", image=image_file, limit=2)
    assert first.image and json.dumps(first.image)
    _add("b", image=image_file, limit=2)
    _add("c", image=image_file, limit=2)
    entries = history.load()
    assert [e.text for e in entries] == ["b", "c"]
    assert not (history.images_dir() / "1.png").exists()
    assert (history.images_dir() / "3.png").exists()


def test_keep_images_off(image_file):
    assert _add("a", image=image_file, keep=False).image is None


def test_corrupt_lines_are_skipped():
    _add("ok")
    with history.history_path().open("a") as fh:
        fh.write("{broken\n\n")
    assert [e.text for e in history.load()] == ["ok"]


def test_clear(image_file):
    _add("a", image=image_file)
    assert history.clear() == 1
    assert history.load() == []
    assert not history.images_dir().exists()


def test_preview_page_escapes_and_bundles_katex():
    page = preview.build("x </script><b>", "latex", "fake", 1.25)
    html = page.read_text()
    assert "</script><b>" not in html
    assert "<\\/script>" in html
    assert (page.parent / "katex" / "katex.min.js").exists()
    assert (page.parent / "katex" / "fonts").is_dir()
    assert "cdn" not in html.lower()
