"""Round trip benchmark: render LaTeX, OCR it back, score it. Plus snip latency.

Usage (from the repo root):
  uv run --group bench python bench/run.py accuracy --backend mlx
  uv run --group bench python bench/run.py latency --backend mlx -n 20
  uv run --group bench python bench/run.py render      # images only, no model

Results go to bench/results/<name>.json. Rendered images go to bench/out/.
Run one model process at a time.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from equations import EQUATIONS  # noqa: E402
from metrics import score  # noqa: E402
from render import RenderError, engine, mathtext_supported, render_equation  # noqa: E402

from snipmd import history, system  # noqa: E402
from snipmd.config import Config  # noqa: E402
from snipmd.engine import Engine  # noqa: E402

OUT = HERE / "out"
RESULTS = HERE / "results"


def machine() -> dict:
    def sysctl(key: str) -> str:
        try:
            return subprocess.run(
                ["sysctl", "-n", key], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except OSError:
            return ""

    mem = sysctl("hw.memsize")
    return {
        "chip": sysctl("machdep.cpu.brand_string") or platform.processor(),
        "memory_gb": round(int(mem) / 2**30) if mem.isdigit() else None,
        "os": f"macOS {platform.mac_ver()[0]}" if sys.platform == "darwin" else platform.platform(),
        "python": platform.python_version(),
    }


def render_all(scale: float = 2.0) -> list[dict]:
    """Render every equation at ``scale`` pixels per point.

    2.0 matches a Retina screen at 100 percent zoom (12 pt text is about
    32 px tall). 1.0 matches a non-Retina screen or a zoomed out page.
    """
    out = OUT / f"x{scale:g}"
    out.mkdir(parents=True, exist_ok=True)
    tool = engine()
    items = []
    for i, (cat, latex) in enumerate(EQUATIONS, 1):
        png = out / f"eq{i:02d}.png"
        if tool == "mathtext" and not mathtext_supported(latex):
            continue
        if not png.exists():
            try:
                render_equation(latex, png, OUT / "tex", scale)
            except RenderError as exc:
                print(f"skip eq{i:02d}: {exc}", file=sys.stderr)
                continue
        items.append({"id": i, "category": cat, "truth": latex, "image": str(png)})
    print(f"rendered {len(items)} equations with {tool} at {scale:g}x", file=sys.stderr)
    return items


def backend_label(eng: Engine, cfg: Config) -> str:
    name = eng.backend.name
    if name == "mlx":
        return f"mlx ({cfg.mlx_model})"
    if name == "ollama":
        return f"ollama ({cfg.ollama_model})"
    return name


def cmd_accuracy(args: argparse.Namespace) -> None:
    items = render_all(args.scale)
    cfg = Config(backend=args.backend)
    eng = Engine(cfg)
    t0 = time.perf_counter()
    eng.warm()
    load_s = time.perf_counter() - t0
    rows = []
    for item in items:
        result = eng.run(Path(item["image"]), "latex")
        s = score(result.text, item["truth"])
        rows.append(
            {**item, "pred": result.text, "raw": result.raw, "seconds": round(result.seconds, 3)}
        )
        mark = "ok " if s["exact"] else "   "
        print(f"{mark} eq{item['id']:02d} cer={s['cer']:.3f}  {result.text}", file=sys.stderr)

    summary = {
        "benchmark": "latex-roundtrip",
        "date": date.today().isoformat(),
        "backend": backend_label(eng, cfg),
        "renderer": engine(),
        "scale": args.scale,
        "model_load_seconds": round(load_s, 2),
        "machine": machine(),
        "rows": rows,
    }
    name = args.name or f"accuracy-{eng.backend.name}-x{args.scale:g}"
    write_accuracy(summary, RESULTS / f"{name}.json")


def write_accuracy(summary: dict, path: Path) -> None:
    """Aggregate per-row scores into the summary and save it."""
    rows = summary["rows"]
    for r in rows:
        r.update(score(r["pred"], r["truth"]))
    n = len(rows)
    exact = sum(r["exact"] for r in rows)
    equiv = sum(r["equivalent"] for r in rows)
    cer = sum(r["edits"] for r in rows) / max(1, sum(r["length"] for r in rows))
    cer_eq = sum(r["edits_equiv"] for r in rows) / max(1, sum(r["length_equiv"] for r in rows))
    by_cat: dict[str, dict] = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {"n": 0, "exact": 0, "equivalent": 0})
        c["n"] += 1
        c["exact"] += int(r["exact"])
        c["equivalent"] += int(r["equivalent"])
    summary.update(
        {
            "n": n,
            "exact_match": exact,
            "exact_match_rate": round(exact / max(1, n), 4),
            "equivalent_match": equiv,
            "equivalent_match_rate": round(equiv / max(1, n), 4),
            "cer": round(cer, 4),
            "cer_equivalent": round(cer_eq, 4),
            "median_seconds": round(statistics.median(r["seconds"] for r in rows), 3),
            "by_category": by_cat,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    for r in rows:
        if not r["equivalent"]:
            print(f"miss eq{r['id']:02d}: {r['pred']}  (truth {r['truth']})", file=sys.stderr)
    print(
        f"{summary['backend']}: exact {exact}/{n} ({exact / max(1, n):.1%}), "
        f"equivalent {equiv}/{n} ({equiv / max(1, n):.1%}), CER {cer:.2%} "
        f"(equivalent {cer_eq:.2%}), median {summary['median_seconds']} s per equation"
    )


def cmd_rescore(args: argparse.Namespace) -> None:
    """Recompute scores from saved predictions, no model needed."""
    for path in sorted(RESULTS.glob("accuracy-*.json")):
        write_accuracy(json.loads(path.read_text()), path)


def cmd_latency(args: argparse.Namespace) -> None:
    """Time what happens after the mouse is released: PNG on disk to clipboard.

    Each run goes through the same steps as a hotkey snip: prepare the crop,
    run the model, post-process, pbcopy, append to history. The images are
    real crops of rendered equations cycled in order.
    """
    items = render_all()
    cfg = Config(backend=args.backend)
    tmp_home = Path(tempfile.mkdtemp(prefix="snipmd-bench-"))
    os.environ["SNIPMD_HOME"] = str(tmp_home)
    eng = Engine(cfg)
    t0 = time.perf_counter()
    eng.warm()
    load_s = time.perf_counter() - t0
    # First call after load includes graph compilation. Time it separately.
    t0 = time.perf_counter()
    eng.run(Path(items[0]["image"]), args.mode)
    first_s = time.perf_counter() - t0
    clip_before = subprocess.run(["pbpaste"], capture_output=True).stdout
    times = []
    for i in range(args.n):
        item = items[(i + 1) % len(items)]
        with tempfile.TemporaryDirectory() as td:
            shot = Path(td) / "snip.png"
            shutil.copyfile(item["image"], shot)
            start = time.perf_counter()
            result = eng.run(shot, args.mode)
            system.copy_to_clipboard(result.text)
            history.add(
                text=result.text,
                mode=result.mode,
                backend=result.backend,
                seconds=result.seconds,
                source="bench",
                image=shot,
            )
            times.append(time.perf_counter() - start)
        print(f"snip {i + 1:02d}: {times[-1]:.3f} s", file=sys.stderr)
    subprocess.run(["pbcopy"], input=clip_before)
    shutil.rmtree(tmp_home, ignore_errors=True)
    times_sorted = sorted(times)
    summary = {
        "benchmark": "snip-latency",
        "date": date.today().isoformat(),
        "backend": backend_label(eng, cfg),
        "mode": args.mode,
        "n": len(times),
        "median_seconds": round(statistics.median(times), 3),
        "p90_seconds": round(times_sorted[int(0.9 * (len(times) - 1))], 3),
        "min_seconds": round(times_sorted[0], 3),
        "max_seconds": round(times_sorted[-1], 3),
        "model_load_seconds": round(load_s, 2),
        "first_snip_seconds": round(first_s, 2),
        "machine": machine(),
        "times": [round(t, 3) for t in times],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    name = args.name or f"latency-{eng.backend.name}"
    (RESULTS / f"{name}.json").write_text(json.dumps(summary, indent=2))
    print(
        f"\n{summary['backend']}: median {summary['median_seconds']} s, "
        f"p90 {summary['p90_seconds']} s over {len(times)} snips, "
        f"model load {load_s:.1f} s, first snip {first_s:.1f} s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render", help="render the equations to bench/out and stop")
    p.add_argument("--scale", type=float, default=2.0, help="pixels per point (default 2)")
    sub.add_parser("rescore", help="recompute scores in bench/results without a model")
    p = sub.add_parser("accuracy", help="OCR every rendered equation in latex mode")
    p.add_argument("--backend", default="mlx", choices=("mlx", "ollama", "auto"))
    p.add_argument("--scale", type=float, default=2.0, help="pixels per point (default 2)")
    p.add_argument("--name", help="results file name")
    p = sub.add_parser("latency", help="time n snips from PNG on disk to clipboard")
    p.add_argument("--backend", default="mlx", choices=("mlx", "ollama", "auto"))
    p.add_argument("--mode", default="latex")
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--name", help="results file name")
    args = parser.parse_args()
    if args.cmd == "render":
        render_all(args.scale)
    elif args.cmd == "accuracy":
        cmd_accuracy(args)
    elif args.cmd == "rescore":
        cmd_rescore(args)
    else:
        cmd_latency(args)


if __name__ == "__main__":
    main()
