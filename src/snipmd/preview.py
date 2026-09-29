"""KaTeX preview: a local HTML page with the result rendered next to the source.

KaTeX ships inside the package, so the page works with no network access.
"""

from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from snipmd import config, system

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>snipmd preview</title>
<link rel="stylesheet" href="katex/katex.min.css">
<style>
  :root { --bg: #fbfbfa; --fg: #1d1d1f; --muted: #6e6e73; --line: #d9d9de; --card: #ffffff; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #1b1b1d; --fg: #ececf0; --muted: #9a9aa2; --line: #38383d; --card: #242427; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; }
  main { max-width: 900px; margin: 0 auto; padding: 24px 16px 48px; }
  header { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  h1 { font-size: 15px; font-weight: 600; margin: 0; }
  .meta { color: var(--muted); font-size: 13px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
          padding: 16px; margin-top: 16px; overflow-x: auto; }
  textarea { width: 100%; min-height: 140px; resize: vertical; border: 0; outline: 0;
             background: transparent; color: var(--fg);
             font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
  button { font: inherit; font-size: 13px; padding: 6px 14px; border-radius: 7px;
           border: 1px solid var(--line); background: var(--card); color: var(--fg);
           cursor: pointer; }
  table { border-collapse: collapse; }
  td, th { border: 1px solid var(--line); padding: 4px 10px; }
  .error { color: #c0392b; font-size: 13px; }
</style>
</head>
<body>
<main>
  <header>
    <h1>snipmd preview</h1>
    <span class="meta" id="meta"></span>
  </header>
  <div class="card" id="rendered"></div>
  <div class="card"><textarea id="src" spellcheck="false"></textarea></div>
  <p><button id="copy">Copy source</button> <span class="meta" id="copied"></span></p>
</main>
<script id="data" type="application/json">__DATA__</script>
<script src="katex/katex.min.js"></script>
<script src="katex/auto-render.min.js"></script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const src = document.getElementById("src");
const out = document.getElementById("rendered");
document.getElementById("meta").textContent =
  data.mode + " mode, " + data.backend + ", " + data.seconds.toFixed(2) + " s";
src.value = data.text;

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function cells(line) {
  const inner = line.trim().replace(/^\\|/, "").replace(/\\|$/, "");
  return inner.split(/(?<!\\\\)\\|/).map(c => c.trim());
}
function markdown(text) {
  const blocks = text.split(/\\n{2,}/);
  return blocks.map(block => {
    const lines = block.split("\\n");
    if (lines.length >= 2 && /^\\s*\\|?\\s*:?-{2,}/.test(lines[1])) {
      const head = cells(lines[0]).map(c => "<th>" + esc(c) + "</th>").join("");
      const body = lines.slice(2).map(l =>
        "<tr>" + cells(l).map(c => "<td>" + esc(c) + "</td>").join("") + "</tr>").join("");
      return "<table><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table>";
    }
    const h = block.match(/^(#{1,6})\\s+(.*)$/);
    if (h) return "<h" + h[1].length + ">" + esc(h[2]) + "</h" + h[1].length + ">";
    return "<p>" + esc(block).replace(/\\n/g, "<br>") + "</p>";
  }).join("");
}
function render() {
  const text = src.value;
  try {
    if (data.mode === "latex") {
      katex.render(text, out, { displayMode: true, throwOnError: true });
      return;
    }
    out.innerHTML = markdown(text);
    renderMathInElement(out, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  } catch (err) {
    out.innerHTML = '<p class="error">' + esc(String(err.message || err)) + "</p>";
  }
}
src.addEventListener("input", render);
document.getElementById("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(src.value);
    document.getElementById("copied").textContent = "Copied";
  } catch (err) {
    src.select();
    document.execCommand("copy");
    document.getElementById("copied").textContent = "Copied";
  }
});
render();
</script>
</body>
</html>
"""


def preview_dir() -> Path:
    return config.home() / "preview"


def _install_assets(target: Path) -> None:
    source = resources.files("snipmd").joinpath("assets", "katex")
    marker = target / "katex" / "katex.min.js"
    if marker.exists():
        return
    with resources.as_file(source) as src_dir:
        shutil.copytree(src_dir, target / "katex", dirs_exist_ok=True)


def build(text: str, mode: str, backend: str, seconds: float) -> Path:
    target = preview_dir()
    target.mkdir(parents=True, exist_ok=True)
    _install_assets(target)
    payload = json.dumps(
        {"text": text, "mode": mode, "backend": backend, "seconds": seconds}, ensure_ascii=False
    ).replace("</", "<\\/")
    page = target / "index.html"
    page.write_text(_PAGE.replace("__DATA__", payload), encoding="utf-8")
    return page


def show(text: str, mode: str, backend: str, seconds: float) -> Path:
    page = build(text, mode, backend, seconds)
    system.open_path(page)
    return page
