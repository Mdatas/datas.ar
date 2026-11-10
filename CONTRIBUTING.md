# Contributing

## Dev setup

```bash
git clone https://github.com/mdatas/datas.ar && cd datas.ar
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,nvidia]"
pytest                                           # about 120 tests, under a minute
datas selftest                                   # this copy checks itself (window, documents, device link…)
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
   user configured — nothing else — and must be listed in `docs/PRIVACY.md`.
5. **Docs with code.** Every user-visible change touches the relevant `docs/*.md`.
6. **Neutral and plain.** The app says what a device can and cannot do (yes / slow / no);
   it does not hide options or decide for the user. Every text a user sees is plain
   language, with acronyms spelled out, in English and Spanish (`tests/test_ui.py` checks
   that both languages have every text). See [docs/UI.md](docs/UI.md).
7. **Few clicks.** A new feature must be usable without reading a manual. If it needs an
   explanation, the explanation goes behind a "more" fold, not in the way.

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
- `tests/test_ui.py` — every text the window asks for exists in English and Spanish, no
  script is written into a page, the page is served with its protections.
- `tests/test_link.py` — two devices pair and talk over the encrypted link; a wrong code
  and an unknown device are refused.
- `tests/test_updates.py` — a real engine switch, and the automatic return when a new build
  fails.
- `tests/test_selftest.py` — `datas selftest`, which every installer build also runs on the
  finished app.
- `scripts/ui_shot.py` — screenshots of every screen without a display (needs the `qt`
  extra); look at them before sending a change to the window.

## Commits

Conventional-ish: `feat:`, `fix:`, `docs:`, `catalog:`, `test:`. Keep PRs single-purpose.

## Releases

1. `datas catalog refresh --write`, bump `KNOWN_GOOD_TAG` after testing a newer
   llama.cpp build, bump `__version__` and `pyproject.toml`.
2. `pytest` on Linux, macOS and Windows (CI does this, and also installs the package the
   way a user would and runs `datas selftest` on it).
3. GitHub → Actions → **release** → Run workflow → type the version. It creates the tag and
   the release and starts the installer builds, which attach their files. Details in
   [docs/UPDATES.md](docs/UPDATES.md).
4. Optional, for `pip install datas-ar`: `python -m build && twine upload dist/*`.
