**English** | [Français](README.fr.md)

# GeoNesClick

AI-assisted geolocation coach for OSINT and GeoGuessr training. It analyses what you see on screen and guides
you, according to a **configurable help level**, towards the useful clues: where to look, what can be seen there,
what it implies.

> **The app's interface is in French for now.** In this README, UI labels are given in English, followed by the
> French label shown on screen in italics the first time, e.g. **Settings** (*Réglages*).

> **Recommended game mode: the classic game** (one map, 5 rounds). It is the only mode whose UI is supported for
> now; the others (challenges, streaks…) may follow.
>
> **Intended use: training** (solo games, unranked maps). The coach never reads the game's data, only the displayed
> image. GeoGuessr's rules forbid third-party tools in ranked games: do not use it in competition.

## Project status

**End-to-end skeleton** ✅ (2026-11-07): shortcut → capture → level 1 locally → level 2 remotely, shown in the
coach window.

| Step | Measured |
|---|---|
| Shortcut → capture | about 0.3 s, GNOME notification with thumbnail and sound |
| Level 1: local StreetCLIP (RTX 3050 Ti) | about 60 ms warm, 846 MB of video memory |
| Level 2: Nemotron 3.5 Super VL (NVIDIA), no reasoning | 3 to 5 s usually, up to 15 s depending on load |
| Map: local PLONK cloud, in the background | about 0.8 s for 512 points, 119 MB of extra video memory |

Features:
- **Four help levels**, shown without a click and adjustable mid-game: where to look ("Look at the colour of the
  centre line."), what the AI sees, the likely countries, the answer with its proof.
- **Check the seed while playing**: "Right" / "Wrong" (*Juste* / *Faux*) on each unverified clue.
- **What the AI sees**: the vision model's clue sheet, including the text read word for word.
- **Marks**: Super+Shift+Z freezes the view in full screen; you circle each clue (street sign, road sign, shop
  sign…), numbered ①, ②… Each mark is cropped from the raw image, enlarged if small, then transcribed word for word
  by the AI. They are your pieces of evidence: the coach's conclusions cite them.
- **"Where was it?"** (*C'était où ?*) after the round: you give the real country and the one you had answered; the
  capture joins the test set, and the coach tracks your progress (countries found, countries to work on,
  StreetCLIP's accuracy) and **your confusions**, with the metas that tell the two countries apart.
- **Settings** in the app, applied on the fly, with the list of NVIDIA models and a "Test this model" button
  (checks that it accepts images and measures its latency).
- **Change the shared window** at any time.
- **Map tab** (level 3 and up): likely countries coloured, countries ruled out by a proof greyed out, and the
  **likely zones** outlined from the positions computed locally by PLONK, with their size and their countries; at
  level 4, strong proof zooms onto its country.

Coming next, in order:
1. Grow the test set (20 to 30 captures through "Where was it?", with urban views for the text).
2. Measure the visible text (transcription by level 2, domains, dialling codes) and closed questions.
3. Automatic detection of the Street View view: **postponed**, see below.
4. Map: outline of the region read by the AI (Natural Earth region outlines, names in several languages), and the
   exact place clicked on the map in "Where was it?" to measure the distances in km.

Does averaging StreetCLIP over several crops (whole image, left, centre, right) help? Measured on the same 5
captures (`spikes/streetclip_tta.py`): no. Top-1 unchanged (3/5), mean probability of the right country down
(49 % → 41 %); the partial crops give more weight to the browser bar. Not kept.

**Can PLONK place the view on a map?** [PLONK](https://github.com/nicolas-dufour/plonk) (CVPR 2025, MIT) samples a
cloud of GPS points from StreetCLIP's vector. Measured on 2026-11-07 on the 5 captures (`spikes/plonk_bench.py`,
512 points); the distance is estimated from the zone noted in the test set:

| Real | StreetCLIP 1st | PLONK 1st (country where most points fall) | Cloud centre | Estimated distance |
|---|---|---|---|---|
| Latvia, west coast of Riga | Estonia (Latvia 2nd) | Poland (Latvia 7th) | Kaliningrad region | ~340 km |
| Serbia, near Bulgaria | Croatia (Serbia 5th) | Croatia (Serbia 11th) | Austria, near Graz | ~700 km |
| Sweden, near Gothenburg | Sweden | Sweden | near Trollhättan | ~90 km |
| Norway, north of Ålesund | Norway | Norway | southern Norway | ~290 km |
| Lithuania, near Vilnius | Lithuania | Lithuania | north-eastern Poland | ~190 km |

- **To pick the country, it brings nothing**: top-1 3/5 like StreetCLIP, top-3 3/5 against 4/5. It reads the same
  vector as StreetCLIP, so it repeats its mistakes (same finding as with the Plonk It tips).
- **For the map, it brings what StreetCLIP does not give**: a position within the country, 90 to 300 km from the
  real place when the country is right, and a spread that tells whether the view can be located (96 km for Norway
  at 99 %, 270 km for the misranked Latvia).
- **Cost**: 119 MB of extra video memory (peak at 987 MB with StreetCLIP); no extra image pass (same `[CLS]` token
  as StreetCLIP, cosine 0.99998 between our fp16 and the training fp32); 3.8 s for 512 points in 250 steps, 0.75 s
  in 50 steps.
- Up to 16 % of the points fall at sea (coasts, borders at 1:50m).
- **How many steps?** Same starting draw, 512 points:

  | Steps | Time | Mean distance from the cloud centre to the one at 250 steps | Countries |
  |---|---|---|---|
  | 250 (paper default) | 3.8 s | — | top-1 3/5 |
  | 100 | 1.5 s | 28 km | identical |
  | **50 (kept)** | **0.75 s** | **20 km** | identical |
  | 25 | 0.37 s | 35 km; Norwegian cloud widened from 96 to 136 km | identical |

  Up to 50 steps, the difference is sampling noise, negligible next to the error to the real place (90 to
  300 km); at 25 steps, the cloud starts to degrade. Time follows the number of steps more than the number of
  points: 128 points at 50 steps take 0.28 s.

Hence the decision: **PLONK serves the map, not the choice of country**. Cloud computed in the background after
StreetCLIP (50 steps, 512 points by default), filtered by the proof, can be turned off. The engine bundles a reduced
version of the PLONK code (see "Map" below), checked identical to the bench: same points, same cloud centre, at 50
as at 250 steps.

Are cropping and masking the game's UI worth it? Measured on 2026-11-07 on 5 classic-game captures
(`spikes/compare_views.py`):

| Variant | Right country 1st | In the top 3 | Mean probability | Country names copied by the AI |
|---|---|---|---|---|
| Whole browser window | 3/5 | 4/5 | 49 % | 0/5 |
| Cropped view | 2/5 | 4/5 | 47 % | 0/5 |
| Cropped view and masked UI | 2/5 | 4/5 | 44 % | 0/5 |

Capturing the **window** (not the screen) is enough: no measurable gain from cropping, and the black masks even
seem to hinder StreetCLIP. Cropping and masks stay available in the configuration; we will measure again with a
larger test set.

Lessons from phase 0 (feasibility tests):
- Making the vision model's prompt longer degrades its text reading: on the "Repkény utca" sign, 8 exact readings
  out of 10 with the current prompt, 4 out of 12 with extra instructions (ignore the game's UI, write
  "unreadable"). The UI text will therefore be filtered by the coach, not by the prompt.
- On the NVIDIA free tier, availability varies: on 2026-11-07, `z-ai/glm-5.3-flash` and
  `meta/llama-3.2-90b-vision-instruct` did not answer; Nemotron Nano Omni answered in 5 s but made up details.
  Hence Nemotron 3.5 Super VL as the default.
- Screen sharing can be stopped from the GNOME indicator: the coach reports it and offers "Restart sharing".
- A third-party `gsettings` (Linuxbrew) may not write to the GNOME settings: the script explicitly calls
  `/usr/bin/gsettings`.

## What GeoNesClick downloads

Every network access of the app is listed in [`engine/src/geonesclick/downloads.toml`](engine/src/geonesclick/downloads.toml),
shown by the first-launch assistant **before any download**, and repeated here. A test checks that every address
written in the code is listed there. The required items (without them the app does nothing) take a single consent;
each option has its own and can be turned off later in the Settings. PyTorch CUDA is chosen if there is an NVIDIA
card, otherwise the CPU version.

| What | From where | Size | Licence | When | What leaves your machine |
|---|---|---|---|---|---|
| Python 3.12 (standalone interpreter, python-build-standalone) **(required)** | `github.com`, `objects.githubusercontent.com` | 30 MB | PSF-2.0 | once, at installation | — |
| The engine's Python libraries (PyTorch, Transformers, FastAPI…), pinned versions checked by hash **(required)** | `pypi.org`, `files.pythonhosted.org` | 3.1 GB | various (BSD, MIT, Apache-2.0…), detailed list package by package in the assistant | once, at installation | — |
| PyTorch for CPU (instead of the CUDA version, if there is no NVIDIA card) **(required)** | `download.pytorch.org` | 200 MB | BSD-3-Clause | once, at installation | — |
| StreetCLIP model (geolocal/StreetCLIP, pinned version, safetensors weights) **(required)** | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 1.7 GB | CC BY-NC 4.0 (non-commercial use) | once, at installation | — |
| GeoNames places directory (cities of more than 1,000 inhabitants) and region names | `download.geonames.org` | 11 MB | CC BY 4.0 (GeoNames) | once, if you accept it | — |
| Villages of a country (full GeoNames directory of the leading country) | `download.geonames.org` | 8 MB | CC BY 4.0 (GeoNames) | on demand | — |
| Plonk It guides (84 pages), then an update check every 30 days | `www.plonkit.net` | 2 MB | no reuse licence: collected for your personal use, never redistributed | once, if you accept it | — |
| PLONK model (nicolas-dufour/PLONK_OSV_5M, pinned version, safetensors) | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 144 MB | MIT | once, if you accept it | — |
| Analysis by the NVIDIA vision model (online API) | `integrate.api.nvidia.com` | — | NVIDIA API terms of use (build.nvidia.com); your API key | on every use | your captures (shrunk to 1,280 px), the crops of your marks and the tips to translate |
| OpenStreetMap map background (tiles) | `tile.openstreetmap.org` | — | data © OpenStreetMap contributors (ODbL); OSMF tile usage policy | on every use | your IP address and the map areas displayed |

Licence to be aware of: StreetCLIP is under **CC BY-NC 4.0**, **non-commercial** use only.

## Requirements

- Ubuntu 24.04 or later, with GNOME (Wayland or Xorg)
- An NVIDIA card with CUDA (recommended; without it, StreetCLIP runs on the CPU, more slowly)
- [Rust](https://rustup.rs), [Node.js](https://nodejs.org) and [pnpm](https://pnpm.io), [uv](https://docs.astral.sh/uv/)
- A free NVIDIA API key: [build.nvidia.com](https://build.nvidia.com)

The system packages (WebKitGTK for Tauri, GStreamer and PipeWire for the capture, headers to compile PyGObject) are
checked by the installation script.

## Installation

```bash
scripts/install.sh                  # checks everything and installs the project's dependencies
scripts/install.sh --with-apt       # also installs the missing system packages (asks for sudo)
scripts/install.sh --setup-shortcut # adds the GNOME shortcuts: capture (Super+Shift+G), marks (Super+Shift+Z)
```

The script can safely be run again, for example after each `git pull`. Then, on first launch, enter your NVIDIA API
key (free on [build.nvidia.com](https://build.nvidia.com), "Get API Key") in **Settings › Analysis**
(*Réglages › Analyse*). It is stored outside the repository, in `~/.config/geonesclick/nvapi.key`, readable by you
only (0600), and is never shown again (only its last 4 characters). The `NVAPI` environment variable, if set, takes
priority. A key still in the old `.env` is **moved** there at startup (the line is removed from the `.env`).

To change the shortcuts: `GNC_SHORTCUT="<Super><Shift>h" GNC_MARK_SHORTCUT="<Super><Shift>m"
scripts/install.sh --setup-shortcut`.

The engine uses a **Python 3.12 managed by uv**, in a virtual environment **isolated** from the system packages. The
GStreamer bindings (PyGObject) are compiled from PyPI at installation, hence the `libgirepository-2.0-dev` and
`libcairo2-dev` packages. Only the GStreamer description files (`gir1.2-*`) come from the system.

## Running

```bash
cd app && pnpm tauri dev
```

The coach window starts the Python engine and stops it when closed. The first time, GNOME asks which window to
share: choose the browser window where you play. The permission is remembered
(`~/.config/geonesclick/screencast.token`). To change it (another browser, screen or resolution), open the
**Settings** tab and click **Change window** (*Changer de fenêtre*, Captures section): the GNOME picker opens again.

During a round, press **Super+Shift+G** (or "Capture", *Capturer*). The coach shows **on its own, without a click**,
the help of the level chosen at the top of its window:

| Level | What is shown |
|---|---|
| 1. Look (*Regarder*) | where to look (clue categories and what to observe there), without naming a country |
| 2. Clues (*Indices*) | + what the AI sees, including the text read word for word |
| 3. Countries (*Pays*) | + likely countries, Map tab with the likely zones, each one's clues, translated Plonk It tips |
| 4. Answer (*Réponse*, default) | + synthesis at the top: country, region if a text names it, and the proof |

At level 4, the Answer card honestly says what the coach knows:
- **an AI reading** (text naming a place, domain, plate…) goes first as **"very likely: read by the AI, to be
  confirmed"**, with what it read; the other countries stay visible. Measured on 2026-11-07 on a "Repkény utca"
  sign (Budapest): out of 8 calls, the model wrongly concluded twice with "strong certainty" (Czechia without having
  read the sign, Slovakia reading "ulica"). A conclusion only becomes **"certain"** (country first, others ruled
  out, `[coach] trust_proof`) once confirmed by a local rule (word specific to a language, domain, dialling code):
  that is the next step;
- **without a reading**, a country is given only if it **stands out** from the look of the view (StreetCLIP): at
  least 40 % and a 15-point lead over the 2nd (`[coach] leader_min`, `leader_margin`). Otherwise: **"Hesitation"**
  between the first ones (e.g. Bulgaria 22 %, Hungary 21 %, Slovakia 16 %, Romania 14 %), without a false winner;
- if the AI reports **unreadable text**, the coach advises zooming on it in the game then capturing again: on a
  Romanian capture, the "Monumentul Eroilor Neamului" sign was unreadable in the whole view, and read exactly
  (Romania) once the zone was cropped and enlarged three times. Hence the marks, below.

### Marks

A detail matters (street sign, road sign, shop sign, number plate)? Press **Super+Shift+Z** (or "Mark",
*Marquer*): the view is frozen and opens in full screen. Draw a rectangle around each clue; they are numbered ①,
②… **Enter** has them read, **Esc** cancels, **Backspace** (or right click) removes the last one. Buttons do the same,
in case GNOME does not give the keyboard to the window.

- Each mark is cropped from the **raw** image, at full resolution, then **enlarged** if small (longest side brought
  to 420 px, ×4 at most: `[marks] upscale_to_px`, `max_upscale`).
- The AI **only transcribes** it, word for word, with what it shows and the alphabet; it names no country. The
  coach concludes, with sourced local rules, citing the marks.
- The marks **complete the round's analysis**: capture first (Super+Shift+G opens the round), mark next. The marks
  window recalls the time of the completed capture, and numbering continues from one frozen view to the next.
  Without a capture, the shortcut says so and freezes nothing.
- In debug mode, each crop is kept (`mark-<id>-<n>.png`) with its reading in the log.
- The marks screen recalls **what is taken into account**, and what is not yet (poles, bollards…).
- **Remove** a mark (wrong reading, failed crop): it no longer counts, the answer is recomputed.

### What the coach concludes from your marks

The AI transcribes; the coach concludes **locally**, with sourced rules (`engine/src/geonesclick/evidence.py`), and
the answer cites the marks that prove it:

| Rule | Example | Effect |
|---|---|---|
| **Alphabet** | Cyrillic | rules out the countries that do not write it (France, even if the AI "read" French on the whole view) |
| **Specific letters** | "ъ" before a consonant, "ő", "ș" | language → **very likely** country |
| **Street words** | "utca", "iela", "-katu", "вулиця" | language → **very likely** country |
| **Place names** (GeoNames) | Благоевград, София | **certain** country, if confirmed by another proof and **no mark contradicts it** |
| **Lone place** | "MANTO" | a mere **clue**: it takes a 2nd nearby place, a letter or a word of the language, or StreetCLIP at 10 % at least (`prior_min`) |
| **Street name** | "Via Paolo Lo Manto", "Main Street" | does not locate the view: its words are not places (shown as "Street", *Rue*) |
| **Country outside the candidates** | Manto → 🇭🇳 | shown, does not count |

Measured on 2026-11-07: in one day, **lone** places were wrong four times (Gare → 🇫🇷🇱🇺, Laas → 🇮🇹, Orion →
🇵🇭🇺🇸, and "Lo Manto", taken from the street name "Via Paolo Lo Manto", → 🇭🇳, which overturned StreetCLIP's Italy
at 96 %), whereas the right conclusions came from **grouped** places.

Why so cautious? Measured on 2026-11-07 on a Bulgarian round: mark ① ("Гърмен 3, Гоце Делчев 10, Благоевград 109,
София 219") was read perfectly, but ②, blurry, was **made up** in plausible Russian ("Домой, Город, Казань"), and
the analysis of the whole view had made up French ("Gare, Centre-ville, Mairie"). With both marks, the coach answers
"Bulgaria, very likely" and flags ②; once ② is removed, "Bulgaria, certain". A common word can also name a place
("Gare": districts in France and Luxembourg), hence the required agreement. Only the candidate countries count
(Moldova does not prevent "ș" from pointing to Romania).

**Position on the map.** The places read are plotted on the map. The distances on a direction sign ("Гърмен 3, Гоце
Делчев 10, Благоевград 109, София 219") give an **estimated position** by triangulation (`locate.py`): they are road
distances, converted to straight-line distances (detour ×1.15 to ×1.45), in relative error, so that the nearby
places pin the point. Measured on this sign: 41.58° N, 23.83° E, 2-3 km from Гърмен, announced within 2 km (no
ground truth yet to confirm it). The AI sometimes misreads a digit ("6" then "8" on the same mark): if the distances
do not agree, **no point**. The coach points out the distance to check and keeps only what stays true (the view is
less than *d* km from the closest place).

**Signs copied column by column.** The AI often copies a direction sign line by line, with the digits apart. The
coach re-reads it as a table (measured on 2026-11-07 on three signs): a distance after the name, on its line, is
never replaced; lone numbers following a block of places go to them in order if there are as many of them ("329
Faaborg", "Glamsbjerg", "28", "3": Faaborg 28, Glamsbjerg 3, the 329 was a road); otherwise a lone number right
under a place goes to it ("SARANSK", "162"); finally, a number before the name counts ("10 Aarup"). An extra number
is a road number, ignored ("5 Ørsted", "329"; "Гърмен 3", "197"). Still undecidable from the text alone: "329
Faaborg" with no other digit; the consistency of the distances flags it.

Limit: a wrong but geometrically plausible digit ("8" for "3" between two neighbouring villages) passes this check,
with a few km of error.

**Namesakes and small villages.** Measured on 2026-11-07 on a round in Béarn: "LAAS" (a village of 108 inhabitants,
missing from the general directory) landed on Lasa, in Italy ("Laas" in German), and wrongly contradicted France;
"ORION" (from L'Hôpital-d'Orion) landed in the Philippines. Hence:
- **proximity**: the places of a round are neighbours. The coach keeps the largest group of places (less than
  400 km from each other, `[rules] place_max_spread_km`) and ignores the distant namesakes, shown struck through;
  without a group of at least two places, nothing is ruled out. Among the namesakes of the group, it keeps the
  closest (Laàs in Béarn, 13 km from Orthez, not Laas in Gers, 87 km away);
- **the villages of the leading country**: as soon as a country leads, its full GeoNames directory (inhabited places
  only; France 7.3 MB, 1.8 s of indexing) is downloaded once, then the marks are re-read (`[rules] detail`). On this
  round: L'Hôpital-d'Orion, Sauveterre-de-Béarn, Orthez and Laàs found, "France, certain". GeoNames then sees which
  country is looked up;
- the comparison ignores Latin accents, hyphens and the leading article ("SAUVETERRE DE BEARN" =
  Sauveterre-de-Béarn, "HOPITAL D'ORION" = L'Hôpital-d'Orion).

The places directory is that of the localities with more than 1,000 inhabitants from
[GeoNames](https://www.geonames.org) (licence [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)),
downloaded once (~11 MB) by `scripts/install.sh` or on first start, then indexed locally (~55 MB, 918,000 names in
all languages). Each rule can be turned off in Settings › Marks (`[rules]`). The region of each place (GeoNames
"admin1" code) is indexed too, with the region names (`admin1CodesASCII.txt`, ~140 KB, downloaded once; offline, the
region is shown by its code): it is used by the locks.

### Locks

At the top of the coach, "**Do you know where you are? Tell the coach**" (*Tu sais où tu es ? Dis-le au coach*): the
list of countries (the most likely first, from level 3); one click, and the line becomes "It's certain: 🇨🇿 Czechia
(you) ✕", then Region and City are chosen the same way. What is certain (the "lock") narrows down the next search:
places and namesakes of the country, villages of the region, map zones and Plonk It tips of the country. Decided on
2026-11-07:

- **the coach** locks the country on its own when your marks make it **certain** (never on "very likely"), and the
  region when the estimated position is a sharp point (sign with consistent distances) and all the places within
  10 km of that point are in the same region (or "within N km of such place", N ≤ 10, when the distances are
  inconsistent: the shortest stays true); without a distance read, when at least two places read are in the same
  region, less than 50 km apart (`region_places_km`). A lone place is not enough. When your places are split
  between regions ("Oker" in Lower Saxony, "Retz" → Rötz in Bavaria), it offers them as buttons. A **city**, it only
  **suggests** ("Laàs?", one click to lock it): a "Pau 40 km" sign precisely names a place where you are not. Its
  locks follow the proofs: a removed mark can undo them;
- **you** can always say "not that" (✕): ruled out for the whole capture, the coach does not suggest it again. You
  can also say it yourself (list or search in the local index, offline; or "it's here" on a place read in your
  marks). The coach never replaces your choice; a chosen city also sets its region and its country;
- **independent opinions stay independent**: the Answer drawn from your marks takes neither your choice nor your ✕
  into account; the banner says whether it confirms it ("✓ your marks confirm it: ① ř, ů, ě") or contradicts it
  ("⚠ your marks point to Poland"), and likewise for StreetCLIP and the AI. That is what reveals a wrong choice.
  Strong contradiction (another "certain" country, or an alphabet that excludes your country): alert at the top and
  two one-click ways out, "Switch to 🇵🇱 Poland" or "① is misread: remove it" (the mistake may come from you or from
  the reading); the coach never changes your choice itself. Your choice only narrows down what follows: namesakes
  kept for the position, region, suggested city;
- a coach lock is only named at the help level that reveals it (country at level 3, region and city at 4); below
  that, the banner says "the coach is sure of it (hidden at this help level)";
- locks **last one capture**: a new capture starts from scratch (a stale lock would skew the next round). In debug
  mode, each lock and each rejection is logged in `capture-<id>.json`.

Settings › What is certain (*Ce qui est sûr*, `[locks]`): activation, country and region set by the coach on its own,
suggested city, radius.

To run the engine alone (without the UI): `cd engine && .venv/bin/python -m geonesclick`.

## Tests

```bash
cd engine && .venv/bin/python -m pytest -q
```

They cover the configuration, cropping and masks, the vision model's answer, the metas and the tie-break, the test
set and the progress, the marks (crop, enlargement, numbering), the settings (allow list, atomic write), and the
server's access rules (origins, Host, CORS preflight, path traversal).

## Configuration

Everything is set in `~/.config/geonesclick/config.toml`, which overrides key by key the commented default values
of [`engine/src/geonesclick/default_config.toml`](engine/src/geonesclick/default_config.toml). Example:

```toml
[coach]
help_level = 2             # where to look + what the AI sees, without naming a country

[capture]
source = "window"               # "window" (default), "monitor" or "both": what GNOME offers to share
sound = false
crop = [0.0, 0.13, 1.0, 0.98]   # analysed zone as fractions [left, top, right, bottom]

[vision]
model = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
```

Each kind of help can be turned off: level 2, seed, "Look…" instructions, "Right" / "Wrong" buttons, answered
country, confusions, notifications, capture copies (sections `[coach]`, `[vision]`, `[metas]`, `[dataset]`,
`[capture]` of the default file). To remove candidate countries: untick them in Settings › Analysis, or
`[streetclip] exclude_countries = ["RU", "UA"]` in the file (it can add countries to the list, but not remove any
otherwise).

**Everything is configurable**, also from the app's **Settings** tab, arranged in collapsible sections (Help,
Analysis, Clues, Map, Capture, Test set, Engine), each with its one-line summary; the fine-grained settings are in
an "Advanced" part. Each change applies and is saved right away (a checkbox, a menu, or a field when leaving it); a
refused value is flagged in place and the screen goes back to the value in effect. The screen only writes to
`config.toml` the values you change, keeping your comments and their order. Candidate countries: untick a country to
rule it out, or add one (English name and ISO code). Two settings only take effect at the next start (StreetCLIP
enabled and its device, what GNOME offers to share): the screen says so.

**The only exception is security**: these settings can only be changed in the file, then by restarting the app.
The screen shows them read-only with their reason:

| Setting | Why file-only |
|---|---|
| `[server]` host, port, allowed_origins | the engine must only listen to your machine and your coach window |
| `[vision]` base_url, api_key_env | a request could redirect your API key to another server |
| `[streetclip]` model, `[plonk]` model, revision | a downloaded model runs on your machine: a booby-trapped model could run code |
| `[map]` tile_url, attribution_url | must also be allowed in the window (CSP and Tauri permissions) |
| folders and files (`directory`, `user_file`, `data_dir`) | a request must not be able to make the app write elsewhere on the disk |

**Debug mode** (Settings › Engine, `[debug] enabled`, off by default): next to each capture, the engine writes a
`capture-<id>.json` log (StreetCLIP countries, zones, what the AI read and its conclusion, timings, "Where was it?"
label), to replay a round afterwards. Local, deleted with the old captures.

A test checks that each configuration key is either editable on screen or in this list: a setting added without
being filed makes the tests fail. The list of NVIDIA models is public:
`curl -s https://integrate.api.nvidia.com/v1/models`.

## Metas

A meta is a visual clue attached to one or more countries. Level 1 picks the **categories that best separate the
likely countries**, weighted by their probabilities: a category that tells the two favourites apart comes before
one that tells two outsiders apart.

Sources, from highest to lowest priority:
1. **Your metas**: `~/.config/geonesclick/mes-metas.toml`, shown as "(your meta)";
2. **The seed** (*amorce*): about fifty well-established facts (alphabets, driving side, colour of the centre line,
   domains), written without a verified source, shown as "(seed, to be checked)".

Format (categories, whose keys are in French: `langue` (language), `conduite` (driving side), `marquage` (road
markings), `poteaux` (poles), `bornes` (bollards), `plaques` (plates), `panneaux` (signs), `domaine` (domain),
`voiture` (car), `vegetation`, `architecture`, `autre` (other)):

```toml
[[meta]]
category = "poteaux"
countries = ["HU"]
hint = "Concrete poles with holes"
look = "the holes in the poles"   # optional: the spoiler-free instruction
verified = true
```

Before revealing the countries, the coach shows for each category **what to observe** ("Look at the colour of the
centre line."), without naming a country: it is the `look` field of the metas, or failing that an instruction
specific to the category.

An error in this file is reported in the Settings screen, without blocking the coach.

**Check the seed while playing.** Each seed clue shown carries two buttons: **Right** adds a verified copy of it to
`mes-metas.toml` (it becomes "your meta, verified"), **Wrong** dismisses it (`[[rejected]]` block, with the category
and the clue's text). The verdicts are appended at the end of the file, without touching the rest: your comments are
kept. To undo, delete the block.

### Plonk It guides

The coach collects the [Plonk It](https://www.plonkit.net) guides **on your machine, for your own use**: the
database is never redistributed or versioned, each installation builds its own. Polite collection: one page at a
time, a 2 s pause (plus a random delay), immediate stop if the site answers 429, and the way Plonk It itself points
to (the `__PRELOADED_DATA__` block of the pages; their API only serves the beginner's guide). The site's
`robots.txt` allows access (`Allow: /`) and only forbids AI training, which the coach does not do.

- **First start**: built in the background (~3 min for 84 countries, about 4,000 tips); the coach works without it
  in the meantime.
- **Afterwards**: one request on the list of guides at most every `refresh_days` days (30 by default), and only the
  modified guides are reloaded. "Update now" button in the Settings.
- **Storage**: `~/.local/share/geonesclick/plonkit/` (raw pages + `plonkit.sqlite`: tips, FTS5 full-text search,
  cached CLIP vectors).
- **At level 1**, when the countries are revealed: for each candidate, the Plonk It tips ranked by similarity with
  the image, with a link to the guide. It is **a lead to check**: the comparison captures the general look of the
  view, not necessarily a precise element (see the measurements below).
- Each tip is filed in a metas category by its Plonk It tags (30 %), then by keywords (`[plonkit] keywords`, 45 %),
  then by the AI for the rest (`ai_classify`, can be turned off): in batches of 25, only once per text (cache), and
  only the 12 known categories are accepted. Measured on 2026-11-07: 1,009 tips classified in 2 min 40; 92 % of the
  tips have a category; about 8 out of 10 are right on a sample, the errors mostly involving the Google camera.

- **Translation**: the guides are in English. The displayed tips are translated on demand into the coach's
  language (`[coach] language`, `fr` by default; `en` = no translation), by the NVIDIA model, with a GeoGuessr
  glossary (bollard → borne, road line → marquage…). The English shows first; the translations arrive in batches of
  3 sent in parallel (~10 s per batch measured with Nemotron Super VL), then are cached: a tip already read shows
  translated immediately. "See the original" lets you compare. Can be turned off (`[plonkit] translate`); model
  configurable (`[plonkit] ai_model`). In practice, on demand is not enough: on 2026-11-07, 31 tips out of 4,060
  were cached, and a round waited more than 2 min for a batch that never came back. Hence:
  - **ahead-of-time translation** of the whole database, in the background, in batches of 10, always after the
    running rounds; it resumes where the cache stops (`[plonkit] pretranslate`, progress in Settings › Clues);
  - **a short timeout** per displayed batch (`[plonkit] translate_timeout_s`, 30 s, no retry): past this timeout,
    or if the model forgets a tip, it stays in English and the coach says so, instead of waiting.
  In debug mode, each batch (duration, tips returned, error) is noted in the round's log.

Manual command: `cd engine && .venv/bin/python -m geonesclick.plonkit collect`.

**Which search engine?** Measured on the 4,060 tips (`spikes/search_bench.py`): an in-memory dictionary, SQLite FTS5
and Tantivy all answer in less than a millisecond (StreetCLIP: 60 ms); Elasticsearch or Meilisearch would only add
one more server. Finding the country by searching the tips for the text of the level 2 sheet fails with every engine
(mean rank ~50th out of 84); comparing the image with the tips (CLIP vectors) ranks the right country 1st or 2nd 4
times out of 5, but does not improve StreetCLIP once merged (same model, redundant signal). Hence SQLite + vectors,
without a dedicated engine.

Observed limit: if StreetCLIP ranks the right country too low (Serbia at 3 %, below the 5 % threshold), no meta can
catch it up. The next levers are independent of StreetCLIP: the visible text and closed questions asked at level 2.

## Map

The window has three tabs, at the bottom: **Coach**, **Map** (*Carte*) and **Settings**; the help levels stay at the
top. The **Map** tab opens from level 3 and fills the whole window; a blue dot lights up on it when new zones are
ready. At levels 1 and 2, the tab is greyed out: the map would reveal the countries. It shows:
- the **likely countries** according to StreetCLIP, the more coloured the more likely;
- with **certain proof**: the proven country in blue, the other candidates greyed out and struck through, and only
  the zones of the proven country, as in the list of countries;
- with **an AI reading** (very likely, to be confirmed): this country is outlined in dotted blue and its zones go
  first; the other countries stay coloured. The Plonk It tips also put it first;
- the **likely zones**: the engine keeps the densest 80 % of the PLONK positions, groups them (two positions less
  than 150 km apart go together) and draws a rounded outline around each group of at least 5 % of the positions.
  Each zone is numbered with its share of the positions; under the map, the list gives its countries and its size
  ("1. 🇸🇪 Sweden · ~450 × 450 km · 50 % of the positions"). It is a lead, not a proof: the zones usually fall
  100–300 km from the place when the country is right.

On the 5 captures of the test set: a zone of ~150 × 200 km in south-western Norway (view north of Ålesund); for
Sweden, a zone around Gothenburg (50 %) and one in Finland (30 %); for Lithuania, a zone straddling Poland and
Lithuania.

The map frames the zones on its own, or the likely countries while the zones are not ready; at level 4, strong proof
narrows it to its country. If the window is maximised, the map takes the full width.

**Map background and privacy.** The background comes from the **online OpenStreetMap** tiles, darkened by a CSS
filter for the coach's theme. The tile server therefore sees your IP address and the areas displayed, roughly the
place of the round. The coach follows OpenStreetMap's
[usage policy](https://operations.osmfoundation.org/policies/tiles/): app-specific User-Agent (`GeoNesClick/0.1`),
attribution always visible, only the displayed tiles are loaded (normal browser cache, no downloading ahead of
time), zoom limited to 13 by default (`[map] max_zoom`, configurable: 13 shows the streets around a position
estimated from your marks; zones and countries are always framed at zoom 8 at most). The darkened background
(inverted colours) becomes unreadable up close (forests and relief as blotches, village names drowned, seen at zoom
13): from zoom 11 (`close_zoom`), the original tiles come back, barely dimmed (`tile_filter_close`). As soon as your
marks locate the view, the PLONK zones are hidden: they only come from the look of the view and would contradict the
proof (north-east France and Aquitaine shown for a round in Béarn). Offline, the map keeps the countries, the cloud
and the places read, without a background.

**Local data.** Country outlines: Natural Earth 1:50m v5.1.2 (public domain), in `engine/src/geonesclick/data/`,
served by the engine (`GET /map/countries`) and used to know in which country each point of the cloud falls
(enclaves included, like Lesotho). PLONK: `nicolas-dufour/PLONK_OSV_5M` weights (safetensors, 144 MB) downloaded
once into the Hugging Face cache on first start; the engine then goes offline. The network code is taken from the
PLONK repository (MIT licence, notice in `engine/src/geonesclick/plonk.py`), reduced to what this model needs: no
extra Python dependency.

**Settings**: `[map]` (activation, tile server, attribution, filter, maximum zoom) and `[plonk]` (activation, steps,
points; zones: `zone_share`, `zone_link_km`, `zone_min_part`). The Settings screen changes the activation, the steps,
the points and the zoom; the tile server, the attribution and the filter can only be changed in the file. **Another
tile server must also be allowed** in the window's security policy (`img-src` of the CSP, in
`app/src-tauri/tauri.conf.json`), and its attribution link in `app/src-tauri/capabilities/default.json`.

## Benchmarks

Each technical choice is measured on the test set before entering the coach. The `spikes/` benches read the copy
versioned in the repository (`engine/dataset/`); the coach saves the new rounds in
`~/.local/share/geonesclick/dataset/`. The benches are in `engine/spikes/` and run from `engine/`:

| Bench | Measures | Command |
|---|---|---|
| `streetclip_bench.py` | video memory, latency and top 5 of StreetCLIP | `.venv/bin/python spikes/streetclip_bench.py [image.png]` |
| `vlm_probe.py` | answer and latency of an NVIDIA vision model | `.venv/bin/python spikes/vlm_probe.py [--model ID] image.png` |
| `compare_views.py` | whole window, cropped view, masked UI | `.venv/bin/python spikes/compare_views.py [--no-vision]` |
| `streetclip_tta.py` | mean over several crops | `.venv/bin/python spikes/streetclip_tta.py` |
| `search_bench.py` | search engines on the Plonk It tips | `uv run --with tantivy==0.26.2 python spikes/search_bench.py` |
| `plonk_bench.py` | PLONK GPS cloud, countries, spread, cost | see below |
| `geonesclick.bench` | marks rules replayed on your rounds: false certainties, region, km | `.venv/bin/python -m geonesclick.bench [--json]` |

**Marks replay bench** (`python -m geonesclick.bench`, from `engine/`). Decided on 2026-11-07: the local rules are
no longer tuned case by case on the last round (the rule written for a Russian sign broke a Danish sign twenty
minutes later), but on the whole set. On each "Where was it?", the coach keeps in
`~/.local/share/geonesclick/dataset/rounds/<id>.json` the text of your marks and what it had concluded; if you paste
the Google Maps link of the true place (the game's end screen), it reads its coordinates (without ever opening it)
and derives the country and region from it. The bench replays all these rounds under the CURRENT rules (same code as
the engine, local index, no network) and counts: certain country right / wrong, very likely, region right / wrong,
position error in km, and whether the true place is within the announced radius. A rule or a threshold only changes
if the bench improves without breaking a round that worked; the target is **zero false certainty**. `--json` to
compare two versions.

**PLONK bench.** PLONK is not a dependency of the coach: its code and dependencies are installed separately, in
`engine/spikes/.vendor/` (ignored by git), without touching the engine's venv.

```bash
scripts/setup-plonk-spike.sh                        # once, then on each version change
cd engine && .venv/bin/python spikes/plonk_bench.py # 512 points by default; otherwise a number as argument
```

The script fetches the PLONK code pinned to a commit, `einops`, `geoopt`, `torchdiffeq` and `scipy` in pinned
versions (without their dependencies: torch and numpy come from the venv) and the Natural Earth v5.1.2 borders. The
bench then downloads the `nicolas-dufour/PLONK_OSV_5M` weights (safetensors, 144 MB) into the Hugging Face cache. It
only loads PLONK's network and sampler, without its `__init__.py`, which would pull in `torchvision` and DINOv2.

## Tools and licences

**GeoNesClick code: [Apache-2.0](LICENSE) licence** (© 2026 MrNesClick). The models and data downloaded on first
launch keep their own licence (see "What GeoNesClick downloads"): in particular **StreetCLIP is under CC BY-NC 4.0,
non-commercial use**, which applies to any use of the app that relies on it.

| Tool | Role | Licence or terms |
|---|---|---|
| [Tauri 2](https://v2.tauri.app), [Vue 3](https://vuejs.org), [Tailwind 4](https://tailwindcss.com) | coach window | MIT / Apache-2.0 |
| [FastAPI](https://fastapi.tiangolo.com), Uvicorn | the engine's local server | MIT / BSD-3 |
| GStreamer, PipeWire, ScreenCast portal (PyGObject) | window capture | LGPL |
| [PyTorch](https://pytorch.org), [Transformers](https://github.com/huggingface/transformers) | running StreetCLIP | BSD-3 / Apache-2.0 |
| [StreetCLIP](https://huggingface.co/geolocal/StreetCLIP) (`geolocal/StreetCLIP`) | level 1, likely countries | **CC BY-NC 4.0: no commercial use** |
| [NVIDIA API](https://build.nvidia.com), Nemotron 3.5 Super VL | level 2, clue sheet | NVIDIA terms of service, personal key |
| SQLite FTS5 | search in the tips | public domain |
| [Plonk It](https://www.plonkit.net) | guides per country | collected locally for your use, never redistributed |
| [PLONK](https://github.com/nicolas-dufour/plonk) (`PLONK_OSV_5M`) | cloud of positions for the map (reduced code bundled) | MIT (code and weights); trained on OSV-5M, Mapillary images CC BY-SA 4.0 |
| [Natural Earth](https://www.naturalearthdata.com) 1:50m | country outlines, country of a point | public domain |
| [Leaflet](https://leafletjs.com) 1.9.4 | the UI's map | BSD-2 |
| [OpenStreetMap tiles](https://www.openstreetmap.org/copyright) | map background, online | ODbL data, attribution required; [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) |
| [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io), [cargo](https://rustup.rs) | installation | MIT / Apache-2.0 |

StreetCLIP's licence alone forbids any commercial use of the coach.

## Maintenance

**Update**: `git pull`, then `scripts/install.sh` (safe to run again: it re-syncs the venv with `uv.lock` and the
front end with `pnpm-lock.yaml`). For the PLONK bench, also run `scripts/setup-plonk-spike.sh` again.

**Change a version**:
- Python dependencies: `cd engine && uv add <package>==<version>` (updates `pyproject.toml` and `uv.lock`), then
  `.venv/bin/python -m pytest -q`;
- front-end dependencies: `cd app && pnpm update <package>`;
- PLONK bench: change `PLONK_COMMIT` and `DEPS` at the top of `scripts/setup-plonk-spike.sh`, run the script again
  then the bench.

**Where the data is** (none of it is versioned):

| Location | Content | If deleted |
|---|---|---|
| `~/.config/geonesclick/config.toml` | your settings | back to the default values |
| `~/.config/geonesclick/mes-metas.toml` | your metas and verdicts on the seed | lost: back it up |
| `~/.config/geonesclick/screencast.token` | GNOME sharing permission | GNOME asks for the window again |
| `~/.local/share/geonesclick/plonkit/` | Plonk It guides, tips, vectors, translations | rebuilt at startup (~3 min, translations redone on demand) |
| `~/.local/share/geonesclick/places/` | GeoNames places directory (CC BY 4.0), indexed | downloaded again at startup if missing (~11 MB) |
| `~/.cache/huggingface/hub/` | StreetCLIP and PLONK weights | downloaded again at the next launch (network required) |
| `~/.local/share/geonesclick/dataset/` | test set (images, `labels.toml`, the bench's `rounds/`) | lost: back it up, it is the basis of all the measurements |
| `~/.local/share/geonesclick/captures/` | round captures; in debug mode, the `capture-<id>.json` log of each analysis | no consequence |
| `engine/spikes/.vendor/` | code and dependencies of the PLONK bench | `scripts/setup-plonk-spike.sh` recreates it |

The test set and the captures lived in `engine/` until 2026-11-07 (read-only in an AppImage): on first launch, the
captures are moved and the test set copied (the copy tracked by git stays in the repository).

**Settings › Storage** (*Stockage*) shows the size of each item and an **Empty** button (*Vider*, in two steps:
Empty, then Confirm, with what it costs; Plonk It warns that the ahead-of-time translations will have to be redone).
The maximum size (`[storage] max_cache_mb`, 500 MB) only applies to the caches **that grow** on their own (villages
of the countries met): the least recently used go first. The base (GeoNames directory, Plonk It guides) never goes
on its own, and your test set, your metas and your config are never emptied. For safety, only files known to the
coach are deleted, never a whole folder.

**Erase everything** (*Tout effacer*, right to erasure, GDPR): at the bottom of Settings › Storage. The list of what
goes is shown with the sizes: API key, settings, your metas, screen-sharing permission, captures and logs, test set
(flagged as precious), Plonk It guides and translations, GeoNames places and villages, UI state, the app's GNOME
shortcuts. A separate box, unticked: also the downloaded models (StreetCLIP, PLONK: nothing personal; other
software's models stay). You have to type "EFFACER"; then the engine and the UI start again from scratch. Only files
known to the app are deleted, never a folder set by hand nor its foreign content. The copy of the test set
versioned in the repository (`engine/dataset/`) is not touched.

**Offline**: once StreetCLIP and PLONK (if enabled) are cached, the engine switches Hugging Face to offline mode at
startup. To get a new version of a model, delete its folder
(`~/.cache/huggingface/hub/models--geolocal--StreetCLIP`, `models--nicolas-dufour--PLONK_OSV_5M`) and restart.

**Update PLONK or Natural Earth**: the weights are pinned to a Hugging Face revision (`[plonk] revision`, the one
that was measured); to change it, replace `revision`, run `spikes/plonk_bench.py` again and compare. The PLONK
network code is pinned in `plonk.py` (commit 76d4641); after a change in the original repository, redo the bench
(`scripts/setup-plonk-spike.sh` with the new commit, then `spikes/plonk_bench.py`) and compare with the engine's
module before modifying it. The outlines come from Natural Earth v5.1.2; for another version, replace
`engine/src/geonesclick/data/ne_50m_admin_0_countries.geojson` (the `ISO_A2_EH` field must exist) and run the tests
again.

**Before each commit**: the tests (`cd engine && .venv/bin/python -m pytest -q`, without any network access), then a
code review and a security review.

## Architecture

```
GNOME shortcut ─► Python engine (FastAPI, 127.0.0.1:47615) ◄─ WebSocket ─► Tauri + Vue window
                     │
                     ├─ capture: ScreenCast portal + PipeWire + GStreamer (continuous stream)
                     ├─ level 1: local StreetCLIP (likely countries) + metas + Plonk It tips
                     │    └─ map: local PLONK on the same vector (cloud of positions, background)
                     └─ level 2: NVIDIA vision model (clue sheet, asynchronous)
Tauri window ── OpenStreetMap tiles (online, map background only)
```

| Component | Choice | Configurable |
|---|---|---|
| UI | Tauri 2 + Vue 3 + Tailwind 4 | — |
| Engine | Python 3.12, FastAPI + WebSocket | port, allowed origins |
| Capture | ScreenCast portal + PipeWire + GStreamer | crop, masks, notification, sound |
| Level 1 | StreetCLIP (`geolocal/StreetCLIP`) | model, prompt, list of countries, top N |
| Level 2 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | model, prompt, reasoning, timeout |
| Metas | your metas, seed, Plonk It guides collected locally (SQLite + CLIP vectors) | activation, refresh, keywords, number of tips |
| Map | Leaflet + OSM tiles; PLONK (`nicolas-dufour/PLONK_OSV_5M`); Natural Earth | activation, steps, points, tile server, filter, zoom |

**Security**: the engine only listens on `127.0.0.1` and refuses any unknown web origin (a website open in the
browser can neither trigger a capture nor read the results). The shortcut's socket is `0600`. The API key only goes
to the NVIDIA API. The coach window only loads external images from `tile.openstreetmap.org` (CSP `img-src`) and
only opens the Plonk It pages and the OpenStreetMap copyright page in the browser.

## Repository layout

```
app/                      Tauri + Vue UI
  src-tauri/src/lib.rs    starts and stops the engine
  src/engine.ts           connection to the engine (WebSocket + HTTP)
  src/components/         countries (Countries), map (CoachMap), what the AI sees (Observations), locks
                          (Locks), "Where was it?" (LabelForm), settings (SettingsPanel + SettingField)…
  src/settingsSchema.ts   description of each setting of the screen (label, help, type, section)
engine/                   Python engine
  src/geonesclick/        capture, StreetCLIP, PLONK (plonk.py), borders (borders.py), vision, metas
                          (+ seed), marks and local rules (marks_engine, evidence, places, locate),
                          locks (locks, locks_engine), test set, settings, server
    data/                 Natural Earth 1:50m country outlines (public domain)
  spikes/                 benchmarks: StreetCLIP, vision model, cropping, multi-crop,
                          search, PLONK (third-party code of the PLONK bench in spikes/.vendor/, ignored)
  dataset/labels.toml     labelled test set (local images in dataset/images/, not versioned)
  dataset/rounds/         the bench's corpus: text of the marks and the coach's conclusion, per round
  captures/               screen captures (ignored by git)
scripts/install.sh        installation
scripts/setup-plonk-spike.sh  dependencies of the PLONK bench, separate from the engine's venv
```
