# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Reject malformed or negative HTTP request body lengths instead of reading until EOF.
- Store Windows settings and history under the user's roaming application data directory.
- Apply JPEG EXIF orientation before preparing images for OCR.

## [0.1.0] - 2026-09-30

First release.

### Added

- Menu bar app for macOS with a global hotkey (default cmd+shift+2), native crosshair capture through `screencapture -i`, clipboard copy, notification and a Recent menu.
- Four output modes: `markdown`, `latex` (bare equation, no delimiters), `table` (Markdown or CSV) and `text`.
- GLM-OCR through mlx-vlm on Apple Silicon and through Ollama anywhere else, selected with `--backend mlx|ollama|auto`.
- Apple Vision fast path for plain text mode.
- Post-processing: code fence stripping, LaTeX delimiter normalisation, removal of the model's token spacing, HTML table conversion, whitespace cleanup.
- Ollama responses are streamed and generation loops are cut, because the glm-ocr build in Ollama 0.34.4 does not stop at its end token.
- Commands: `snipmd`, `snipmd snip`, `snipmd FILE`, `snipmd serve`, `snipmd history`, `snipmd config`, `snipmd doctor`, `snipmd pull`. JSON output with `--json`.
- Local HTTP API on 127.0.0.1 with `/ocr`, `/snip`, `/history` and `/health`. Cross-origin browser requests are refused.
- Offline KaTeX preview page. KaTeX is bundled, nothing is fetched from a CDN.
- `bench/` with a 48 equation LaTeX round trip benchmark and a snip latency harness.
