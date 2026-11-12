# Contributing

Thanks for helping. GeoNesClick is a small project: open an issue first for anything beyond a small fix, so we can
agree on the approach before you spend time on it.

## Set up

Follow [docs/development.md](docs/development.md) to build from source and run the app (Ubuntu 24.04 or later, GNOME).
[docs/architecture.md](docs/architecture.md) explains how its Rust, Vue and Python parts fit together.

## Before you send a change

- Run the tests from the repository root; they need no network and no display:

  ```bash
  (cd engine && .venv/bin/python -m pytest -q)
  (cd app && npx vue-tsc --noEmit)
  (cd app/src-tauri && cargo test --lib)
  (cd app && pnpm exec playwright test)   # interface tests, once: pnpm exec playwright install webkit
  ```

- Add a line to the `[Unreleased]` section of [CHANGELOG.md](CHANGELOG.md) when the change is visible to the
  people who use the app, written for them.
- Code, comments, commit messages and documentation are in English. Texts shown to the player are never written in
  the code: they go in the catalogs (below).
- A commit says in its first line what it does ("Reopen the GNOME picker when restarting the sharing"), and in its
  body why.

## Translations

Every text the player sees is in `engine/src/geonesclick/locales/<lang>.json`, one file per language, shared by the
engine, the interface and the installer. `en.json` is the reference.

- To fix a translation, edit the value in the language's file.
- To add a language, copy `en.json` to `<code>.json` and translate the values; the three layers find the file on
  their own. If the code is not one of `en, fr, es, de, it, pt`, add it to `[coach] language` in
  `engine/src/geonesclick/config.py`.
- Keep the keys and the `{placeholders}` as they are: `tests/test_i18n.py` checks that every catalog has the same
  keys and placeholders as `en.json`.

## Prompts and measurements

The prompts sent to the vision model are measured (see [docs/benchmarks.md](docs/benchmarks.md)): a longer or
reworded prompt can read signs worse. A change to a prompt comes with a run of `engine/spikes/prompt_bench.py` before
and after.

## Security

Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contribution is licensed under the [Apache License 2.0](LICENSE), like the rest
of the code.
