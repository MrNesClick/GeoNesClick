# Changelog

What changes from one version of GeoNesClick to the next, for the people who use it. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The release workflow publishes each version's section as
its release notes.

## [Unreleased]

## [0.2.0] - 2026-11-12

### Added

- **The interface is in English and French.** The language is chosen on the first screen of the installer and can be
  changed at any time in Settings › General; the change applies right away, and the AI answers in that language.
- Spanish, German, Italian and Portuguese still translate the Plonk It tips; their interface is in English until
  their translation is added (one file per language, `engine/src/geonesclick/locales/`).
- When the installation of the engine fails, the installer names the cause: the download site that does not answer
  (GitHub, PyPI, PyTorch or Hugging Face) or a full disk. Downloads are tried 6 times before giving up, and "Retry"
  keeps what is already downloaded.

### Changed

- **English is the default language.** An existing installation switches to English: pick French again in Settings ›
  General.
- "Restart sharing", after you stopped the screen sharing from GNOME, opens the window picker again instead of
  resuming the previous window (which could fail with "target not found"). Only the app's start resumes the
  remembered window without asking.
- The first settings group is called "General" (help level, language, proof rule).
- The prompts sent to the vision model are in English, measured to read signs as well as the previous ones
  (accents included); the coach's own texts no longer depend on the words the model writes.
- Your metas file is `~/.config/geonesclick/my-metas.toml`; the seed clues have stable ids, so your "Right" /
  "Wrong" verdicts survive a change of language.

### Fixed

- The size column of the installer no longer wraps.

### Migration

Your files from 0.1 are converted once, at the first start of 0.2.0, each with a `.before-0.2` backup next to it:
`mes-metas.toml` becomes `my-metas.toml` (your verdicts on the seed are kept), the category names in `config.toml`
are updated, and the Plonk It cache is converted in place (its AI classifications and translations are kept). A vision
or marks prompt you had customised for 0.1 is removed, because it asked for the old answer format: the default one
applies again. A file that cannot be converted is left as it is and reported in the Settings. Going back to 0.1.1
means restoring those backups.

## [0.1.1] - 2026-11-08

### Fixed

- Installer and settings texts found wrong on a clean Ubuntu 26.04 without an NVIDIA card (where PLONK's memory goes,
  where the engine and the AI models are stored).
- The Hugging Face warning about unauthenticated requests no longer shows in the installation log.

### Changed

- The README gives the memory needed and where the files are stored.
- The release build retries the GitHub downloads and pins the AppImage runtime.

## [0.1.0] - 2026-11-08

First release.

### Added

- AppImage for Ubuntu 24.04 or later with GNOME, with a first-launch installer that lists everything it downloads
  (what, from where, size, licence) before the first byte, then installs the engine in `~/.local/share/geonesclick/`.
- Screen capture of the game window (Super+Shift+G), help by level from "Look" to "Answer", likely countries from
  StreetCLIP (local), what the remote vision model reads, and the metas that tell the likely countries apart.
- Marks (Super+Shift+Z): circle a sign, the AI copies its text, local rules conclude (alphabet, letters, street
  words, GeoNames places, distances on direction signs).
- Locks: tell the coach the country, region or city you are sure of.
- Map tab with the likely zones computed locally (PLONK) and the places read on your marks.
- Plonk It tips matching the view, translated on demand.
- "Where was it?" after the round, to build a test set and follow your progress.
- Every setting editable in the app; "Erase everything" removes all your data.

[Unreleased]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MrNesClick/GeoNesClick/releases/tag/v0.1.0
