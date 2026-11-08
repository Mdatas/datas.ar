# Contributing

## Dev setup

```bash
git clone https://github.com/mdatas/datas.ar && cd datas.ar
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,nvidia]"
pytest                                           # unit tests (~2 s)
DATAS_HOME=/tmp/datas-dev datas install          # fetch llama.cpp once …
DATAS_HOME=/tmp/datas-dev pytest                 # … and the integration test runs too
ruff check . && ruff format --check .
```

`DATAS_HOME` keeps your development state away from your real install.

## Layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#code-map). One module per concern; the
orchestrator is the only place that knows about all of them.

## Rules of the house

1. **No invented data.** Catalog sizes come from the Hugging Face API, hardware values
   from the device, speeds from `llama-bench`. If something cannot be read, it is `None`
   and the UI says "unknown". Estimates are allowed only where documented and flagged
   (`kv_exact: false`).
2. **No AI in the decision path.** The recommender stays arithmetic; tests assert the
   picks for reference devices (`tests/test_recommender.py`). Change a threshold → update
   the doc table in `docs/RECOMMENDER.md` and the test in the same PR.
3. **Reuse upstream.** If llama.cpp grows a flag that replaces our logic (as `--fit` did
   for layer placement), prefer the flag and delete our code.
4. **Local by default.** New network calls go to GitHub, Hugging Face or a provider the
   user configured — nothing else — and must be listed in README › Privacy.
5. **Docs with code.** Every user-visible change touches the relevant `docs/*.md`.

## Adding a catalog model

See [docs/CATALOG.md](docs/CATALOG.md#adding-a-model). Prefer `ggml-org` repos. Run
`datas catalog refresh` before committing so `verified` dates are current, and keep the
two-quants rule unless there's a reason not to.

## Tests

- `tests/test_recommender.py` — the picks for 5 reference devices; add yours if you own
  an interesting one.
- `tests/test_runtime.py` — asset matching against the real b11669 asset list; update
  when upstream renames assets.
- `tests/test_gguf_and_server.py` — builds a 460 KB synthetic llama GGUF
  (`tests/make_tiny_gguf.py`) and runs the real `llama-server` through our process
  manager. Skipped when the runtime isn't installed.
- `tests/test_api.py` — FastAPI routes via `TestClient`.

## Commits

Conventional-ish: `feat:`, `fix:`, `docs:`, `catalog:`, `test:`. Keep PRs single-purpose.

## Releases

1. `datas catalog refresh --write`, bump `KNOWN_GOOD_TAG` after testing a newer
   llama.cpp build, bump `__version__` and `pyproject.toml`.
2. `pytest` on Linux, macOS and Windows (CI does this).
3. `python -m build && twine upload dist/*`.
