"""Snip history as a JSON Lines file, newest last, plus optional crop images."""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from snipmd import config

_LOCK = threading.Lock()


@dataclass
class Entry:
    id: int
    time: str
    mode: str
    backend: str
    seconds: float
    source: str
    text: str
    image: str | None = None


def history_path() -> Path:
    return config.home() / "history.jsonl"


def images_dir() -> Path:
    return config.home() / "images"


def load() -> list[Entry]:
    path = history_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            entries.append(Entry(**{k: data.get(k) for k in Entry.__dataclass_fields__}))
        except (json.JSONDecodeError, TypeError):
            continue
    return entries


def _write(entries: list[Entry]) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in entries))
    tmp.replace(path)


def add(
    *,
    text: str,
    mode: str,
    backend: str,
    seconds: float,
    source: str,
    image: Path | None = None,
    limit: int = 500,
    keep_image: bool = True,
) -> Entry:
    with _LOCK:
        entries = load()
        next_id = (entries[-1].id + 1) if entries else 1
        saved: str | None = None
        if keep_image and image is not None and image.exists():
            images_dir().mkdir(parents=True, exist_ok=True)
            target = images_dir() / f"{next_id}{image.suffix or '.png'}"
            shutil.copyfile(image, target)
            saved = str(target)
        entry = Entry(
            id=next_id,
            time=datetime.now().isoformat(timespec="seconds"),
            mode=mode,
            backend=backend,
            seconds=round(seconds, 3),
            source=source,
            text=text,
            image=saved,
        )
        path = history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        entries.append(entry)
        if limit and len(entries) > limit:
            drop, keep = entries[:-limit], entries[-limit:]
            for old in drop:
                if old.image:
                    Path(old.image).unlink(missing_ok=True)
            _write(keep)
        return entry


def get(entry_id: int) -> Entry | None:
    for entry in load():
        if entry.id == entry_id:
            return entry
    return None


def recent(n: int = 20) -> list[Entry]:
    entries = load()
    return entries[-n:][::-1] if n > 0 else entries[::-1]


def clear() -> int:
    with _LOCK:
        entries = load()
        history_path().unlink(missing_ok=True)
        if images_dir().exists():
            shutil.rmtree(images_dir(), ignore_errors=True)
        return len(entries)
