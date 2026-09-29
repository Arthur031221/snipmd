# Contributing

Bug reports with a sample image are the most useful contribution. Attach the crop (see `snipmd history --json` for its path) and the output you expected.

## Setup

```sh
git clone https://github.com/Arthur031221/snipmd
cd snipmd
uv sync
uv run snipmd doctor
```

## Before you open a pull request

```sh
uv run ruff check .
uv run ruff format .
uv run pytest
```

The test suite mocks the OCR backend and finishes in well under a minute. It does not need a model.

If you touch recognition or post-processing, run the benchmark and put the before and after numbers in the pull request:

```sh
uv run --group bench python bench/run.py accuracy --backend mlx
```

## Guidelines

- Keep the dependency list short. Every new package needs a reason.
- Anything that shells out must check the tool exists and print a clear message if it does not.
- Post-processing rules need a test in `tests/test_postprocess.py` with the raw model output that motivated them.
- Numbers in the README come from `bench/` and carry the method. Do not add numbers you did not measure.
