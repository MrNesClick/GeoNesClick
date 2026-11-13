# Rules for working on GeoNesClick

These rules apply to every change, whoever (or whatever) writes it. The rest is in
[CONTRIBUTING.md](CONTRIBUTING.md) and [docs/development.md](docs/development.md).

## Identity

- The only identity in this repository is **MrNesClick** (`contact@mrnesclick.fr`): commit author and committer,
  tagger, copyright, docs.
- The maintainer's real name, local username, personal email addresses and local paths (`/home/...`) never appear
  anywhere: files, commit messages, tags, release notes, issue texts, screenshots, logs attached to the repository.
  Neither does the app's former name.
- Check before every push. The maintainer's clone has a local `pre-push` hook (in `.git/hooks`, never committed)
  that refuses a push whose files, commits or tags contain the real name.

## Branches

- Never commit on `main`: it is the public, released code, and it only moves when a release is published.
- Each piece of work has its branch: `work/<version>` for the next release (`work/0.5.0`), or a topic name for work not
  tied to one. Commit there, after the reviews; the branch may be pushed with tracking (`git push -u`): a branch
  push publishes nothing (the release workflow runs on `v*` tags only).
- A release happens on its branch: version commit, local AppImage, test in the VM; then `main` is fast-forwarded to
  the branch and pushed with the annotated tag (see [docs/development.md](docs/development.md#publish-a-release)).

## French texts

- The French texts shown to users (catalog `engine/src/geonesclick/locales/fr.json`, `README.fr.md`) say "vous", never
  "tu": "Vous pouvez supprimer…", "Choisissez…".

## Changelog

- Every change to what the application does adds a line to `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), in
  the same commit, written for the people who use it (what changes for them, not how it is coded).
- Only the application itself goes in it: a feature, a behaviour, a fix, a setting, what it sends or stores. Not the
  repository's rules or process (branches, reviews), the documentation, the wording or tone of texts, tests or tools.
- A release moves those lines under `## [x.y.z] - YYYY-MM-DD`, in the order Added, Changed, Deprecated, Removed,
  Fixed, Security (then Migration if needed), and updates the comparison links at the bottom of the file.
- Each section becomes the release notes on GitHub: links in it are absolute (`https://github.com/...`), since
  relative links break there. `scripts/release-notes.sh x.y.z` prints what will be published.
- Releases are built by the GitHub Action only, from an annotated `v*` tag (see docs/development.md).

## Versions

Strict [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html), read from the version's CHANGELOG section:

- **PATCH** (0.3.0 → 0.3.1): only `Fixed` (and `Security`) entries.
- **MINOR** (0.3.1 → 0.4.0): any `Added`, `Changed` or `Deprecated` entry, compatible with the previous version.
- **MAJOR** (1.x → 2.0.0): anything that breaks, listed under `Removed` or flagged in `Changed`: a setting or a data
  file the new version no longer reads without a migration, a raised system requirement (glibc, GNOME, a
  distribution), a removed feature. Before 1.0.0, a breaking change raises the MINOR instead.
