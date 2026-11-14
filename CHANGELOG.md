# Changelog

What changes from one version of GeoNesClick to the next, for the people who use it. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The release workflow publishes each version's section as
its release notes.

## [Unreleased]

### Changed

- In a wide window (1024 pixels and more), the coach shows two columns: what helps you decide (locks, answer, marks,
  where to look or the countries, what tells them apart, Plonk It tips) on the left, the evidence (the capture, what
  the AI sees, after the round) on the right. There the capture is open by default; whether you open or collapse it
  is remembered apart from the narrow window. A narrower window keeps the single column.

## [0.5.0] - 2026-11-13

### Added

- GeoNesClick tells you when a newer version is out: at most once a day, it asks GitHub which version is the latest
  (your IP address and the app's version leave, nothing else; nothing is downloaded on its own). A banner offers the
  release page; **Later** closes it for that version, and Settings › General keeps saying it, with **Check** and the
  option to turn the check off. The installer offers it, ticked; if you update from an earlier version, the coach
  tells you once that it is on.
- A capture that is nearly a single colour (black, a loading screen) or the same image as the previous capture (a
  frozen screen sharing) is still analysed, but comes with a note under the capture and in its summary line, so a
  worthless answer does not pass for a real one.

### Changed

- Opening a newer AppImage now asks once whether to update, showing what changed and what it would download (often
  nothing), with **Later** to keep the installed version. Your settings, your API key and your data are kept (they
  were reset to the recommended choices, and the key asked again), and only the libraries that changed are
  downloaded (a few MB instead of 3.1 GB with an NVIDIA card). While it runs, a single line says what it does,
  naming what it downloads and its size; then the coach offers, once, what changed since your version. Opening an
  older AppImage than the installed one changes nothing and offers to open the installed one.
- GeoNesClick is now installed as `~/.local/share/geonesclick/GeoNesClick.AppImage` and launched from there by the
  applications menu: the file you downloaded can be renamed, moved or deleted (the coach tells you so once), and
  the menu entry no longer breaks when you do. Erase everything removes that copy with the engine.
- The coach no longer shares the game window as soon as it opens: nothing is shared until you click **Share the
  game window**, which then shares the remembered window without GNOME's dialog.
- A country read in your marks is "certain" (put first, the others ruled out, locked by the coach) only when a
  second source seconds the reading: a second mark, or the look of the view (StreetCLIP giving that country 10 % or
  more). One mark alone is otherwise "very likely", and the answer says that a second mark would settle it: a single
  blurry crop can be made up whole and still be coherent.

### Fixed

- When the window shared last time no longer exists, sharing it no longer shows "screen sharing active" with no image
  coming: the coach forgets that window and opens the GNOME picker so you can choose the game window. The sharing
  counts as active from its first image only.
- The local AI starts on a capture without waiting for its copy on disk to be written: its answer comes about 0.35 s
  sooner on a 1920-pixel-wide screen, 1.3 s in 4K. The "capture taken" notification comes once the copy is written.

## [0.4.1] - 2026-11-13

### Security

- The browser's bars (tab titles, address, bookmarks) no longer leave with your captures for the NVIDIA vision
  model, nor reach the local AI. The coach finds where the game page starts from the first capture, by the line the
  browser draws under its bars, and also by comparing captures, which works whatever the browser. If neither finds
  it, it cuts a fixed share of the top of the window and tells you under the capture. A zone set by hand in
  `config.toml` (`[capture] crop`) still takes precedence.

### Fixed

- A browser window resized after the screen sharing started is now analysed without the black bands around it.
  GNOME keeps the shared image at its first size and fills the rest with black: the local AI and the vision model saw
  those bands as part of the view.

## [0.4.0] - 2026-11-13

### Changed

- Without a proof read on the view, the coach names a country as the answer only when the look of the view
  (StreetCLIP) gives it at least 70 % (40 % until now). On the test set, every answer above 70 % was right, while 3
  out of 8 between 40 and 70 % were wrong; below 70 %, the coach talks of hesitation between the first countries. The
  threshold can still be changed in the Settings.

## [0.3.2] - 2026-11-13

### Fixed

- With `XDG_CACHE_HOME` set, the coach looked for the AI models in the wrong folder: the local analysis contacted
  Hugging Face at each start instead of staying offline, and "Erase everything" left the models on the disk (1.7 GB
  for StreetCLIP).
- The installer names the folders where the engine and the models actually go, when `XDG_DATA_HOME`, `HF_HOME` or
  `XDG_CACHE_HOME` point elsewhere.

## [0.3.1] - 2026-11-13

### Fixed

- The keyboard shortcuts did nothing when the path of the home folder (or of `XDG_DATA_HOME`) holds a space. The
  shortcuts already added are repaired at the next launch, with nothing to do.
- When the installer could not add the keyboard shortcuts or the menu entry, it went on to the coach without saying
  so. It now shows the error on its last step, and the coach starts with "Launch anyway".

## [0.3.0] - 2026-11-12

### Added

- GeoNesClick can be added to the applications menu, which also gives it its own icon in the dock instead of a
  generic one: an option of the installer, off by default. The entry follows the AppImage when it is opened from
  another place, and "Erase everything" removes it.
- A "GNOME integration" group in the Settings turns the keyboard shortcuts and the menu entry on or off at any time.

### Fixed

- The "Marks" group of the Settings shows a one-line summary, like the other groups.
- After uninstalling from "Erase everything", no empty `geonesclick` folder is left in `~/.local/share`, and the
  storage summary no longer shows the size measured before.

## [0.2.5] - 2026-11-12

### Fixed

- "Erase everything" with the models box left their weights on the disk (1.7 GB for StreetCLIP) and showed their
  size as a few MB: the recent Hugging Face library keeps them in a shared store, which is now counted and emptied
  (never a file another program still uses).
- After uninstalling from "Erase everything", the storage list no longer shows the sizes measured before.
- The help of the cache size no longer announces features that do not exist.

## [0.2.4] - 2026-11-12

### Added

- "Erase everything" can also remove the engine installed by the AppImage: with the models box too, a full
  uninstall from the app, after which only the AppImage is left.

### Changed

- Marks: the interface says "draw a box around" a clue, since you draw a rectangle.

### Fixed

- The help of "A proof read settles it" named local rules that do not exist (domain, dialling code).
- The list of what is sent to NVIDIA now includes the Plonk It tips it classifies and translates.
- The installer said "nothing is changed in the system" right after installing a missing system component.

## [0.2.3] - 2026-11-12

### Changed

- A missing system component is installed with one click on more systems: through `apt` (Debian, Ubuntu), `dnf`
  (Fedora), `pacman` (Arch) or `zypper` (openSUSE), with each one's package names; the command shown is that of your
  system.

### Fixed

- The Settings screen no longer stays on "Loading the settings…" when it was opened while the engine was still
  starting (first launch): it loads once the engine answers.
- Without an NVIDIA card, the first captures no longer wait minutes for the Plonk It tips to be prepared (about 5
  minutes on a 4-core processor, once): a capture now waits under a second, and the coach shows the preparation's
  progress until the tips close to the view appear.

## [0.2.2] - 2026-11-12

### Added

- When a system component is missing (`libgirepository-2.0-0` on a fresh Ubuntu 24.04), the installer installs it
  with one click after asking for your password; the command to type yourself is still shown.

### Fixed

- The installation of the engine no longer fails at the AI model step ("No module named 'httpx'", 0.2.0 and 0.2.1).

## [0.2.1] - 2026-11-12

### Changed

- GeoNesClick has its own icon (a pin in a crosshair over contour lines) instead of Tauri's logo.

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

[Unreleased]: https://github.com/MrNesClick/GeoNesClick/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/MrNesClick/GeoNesClick/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.5...v0.3.0
[0.2.5]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MrNesClick/GeoNesClick/releases/tag/v0.1.0
