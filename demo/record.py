"""Record the real recognition result used by demo/make_gif.py.

Loads the model, runs the demo crop once to warm up, then times a second
run the way the menu bar app sees it (model already loaded).

  uv run python demo/record.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from snipmd.config import Config
from snipmd.engine import Engine

HERE = Path(__file__).resolve().parent


def main() -> None:
    cfg = Config(backend="mlx")
    engine = Engine(cfg)
    engine.warm()
    engine.run(HERE / "crop.png", "latex")
    result = engine.run(HERE / "crop.png", "latex")
    data = {
        "text": result.text,
        "raw": result.raw,
        "seconds": round(result.seconds, 2),
        "backend": f"{result.backend} ({cfg.mlx_model})",
        "date": date.today().isoformat(),
    }
    (HERE / "crop.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
