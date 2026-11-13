[← README](../README.md)

# How it works

## The Answer card (level 4)

At level 4, the Answer card honestly says what the coach knows:
- **an AI reading** (text naming a place, domain, plate…) goes first as **"very likely: read by the AI, to be
  confirmed"**, with what it read; the other countries stay visible. Measured on a "Repkény utca"
  sign (Budapest): out of 8 calls, the model wrongly concluded twice with "strong certainty" (Czechia without having
  read the sign, Slovakia reading "ulica"). A conclusion only becomes **"certain"** (country first, others ruled
  out, `[coach] trust_proof`) when the local rules confirm it on your marks (see below);
- **without a reading**, a country is given only if it **stands out** from the look of the view (StreetCLIP): at
  least 70 % and a 15-point lead over the 2nd (`[coach] leader_min`, `leader_margin`; from 58 % the lead always
  holds, so it only acts with a lower `leader_min`). Otherwise: **"Hesitation"**
  between the first ones (e.g. Bulgaria 22 %, Hungary 21 %, Slovakia 16 %, Romania 14 %), without a false winner;
- if the AI reports **unreadable text**, the coach advises zooming on it in the game then capturing again: on a
  Romanian capture, the "Monumentul Eroilor Neamului" sign was unreadable in the whole view, and read exactly
  (Romania) once the zone was cropped and enlarged three times. Hence the marks, below.

## Marks

A detail matters (street sign, road sign, shop sign, number plate)? Press **Super+Shift+Z** (or the **Mark**
button): the view is frozen and opens in full screen. Draw a box around each clue; they are numbered ①,
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

## What the coach concludes from your marks

The AI transcribes; the coach concludes **locally**, with sourced rules (`engine/src/geonesclick/evidence.py`), and
the answer cites the marks that prove it:

| Rule | Example | Effect |
|---|---|---|
| **Alphabet** | Cyrillic | rules out the countries that do not write it (France, even if the AI "read" French on the whole view) |
| **Specific letters** | "ъ" before a consonant, "ő", "ș" | language → **very likely** country |
| **Street words** | "utca", "iela", "-katu", "вулиця" | language → **very likely** country |
| **Place names** (GeoNames) | Благоевград, София | **certain** country, if confirmed by another proof, **seconded** by a 2nd mark or by StreetCLIP at 10 % at least (`prior_min`), and **no mark contradicts it** |
| **Lone place** | "MANTO" | a mere **clue**: it takes a 2nd nearby place, a letter or a word of the language, or StreetCLIP at 10 % at least (`prior_min`) |
| **Street name** | "Via Paolo Lo Manto", "Main Street" | does not locate the view: its words are not places (shown as "Street") |
| **Country outside the candidates** | Manto → 🇭🇳 | shown, does not count |

Measured: in one day, **lone** places were wrong four times (Gare → 🇫🇷🇱🇺, Laas → 🇮🇹, Orion →
🇵🇭🇺🇸, and "Lo Manto", taken from the street name "Via Paolo Lo Manto", → 🇭🇳, which overturned StreetCLIP's Italy
at 96 %), whereas the right conclusions came from **grouped** places.

Why so cautious? Measured on a Bulgarian round: mark ① ("Гърмен 3, Гоце Делчев 10, Благоевград 109,
София 219") was read perfectly, but ②, blurry, was **made up** in plausible Russian ("Домой, Город, Казань"), and
the analysis of the whole view had made up French ("Gare, Centre-ville, Mairie"). With both marks, the coach answers
"Bulgaria, very likely" and flags ②; once ② is removed, "Bulgaria, certain" if the view also looks Bulgarian to
StreetCLIP. A single crop can be made up whole and still be coherent, as ② was: one mark alone is only "very likely"
unless a 2nd mark or the look of the view seconds it. A common word can also name a place ("Gare": districts in
France and Luxembourg), hence the required agreement. Only the candidate countries count
(Moldova does not prevent "ș" from pointing to Romania).

**Position on the map.** The places read are plotted on the map. The distances on a direction sign ("Гърмен 3, Гоце
Делчев 10, Благоевград 109, София 219") give an **estimated position** by triangulation (`locate.py`): they are road
distances, converted to straight-line distances (detour ×1.15 to ×1.45), in relative error, so that the nearby
places pin the point. Measured on this sign: 41.58° N, 23.83° E, 2-3 km from Гърмен, announced within 2 km (no
ground truth yet to confirm it). The AI sometimes misreads a digit ("6" then "8" on the same mark): if the distances
do not agree, **no point**. The coach points out the distance to check and keeps only what stays true (the view is
less than *d* km from the closest place).

**Signs copied column by column.** The AI often copies a direction sign line by line, with the digits apart. The
coach re-reads it as a table (measured on three signs): a distance after the name, on its line, is
never replaced; lone numbers following a block of places go to them in order if there are as many of them ("329
Faaborg", "Glamsbjerg", "28", "3": Faaborg 28, Glamsbjerg 3, the 329 was a road); otherwise a lone number right
under a place goes to it ("SARANSK", "162"); finally, a number before the name counts ("10 Aarup"). An extra number
is a road number, ignored ("5 Ørsted", "329"; "Гърмен 3", "197"). Still undecidable from the text alone: "329
Faaborg" with no other digit; the consistency of the distances flags it.

Limit: a wrong but geometrically plausible digit ("8" for "3" between two neighbouring villages) passes this check,
with a few km of error.

**Namesakes and small villages.** Measured on a round in Béarn: "LAAS" (a village of 108 inhabitants,
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
downloaded once (~11 MB) on first start, then indexed locally (~55 MB, 918,000 names in
all languages). Each rule can be turned off in Settings › Marks (`[rules]`). The region of each place (GeoNames
"admin1" code) is indexed too, with the region names (`admin1CodesASCII.txt`, ~140 KB, downloaded once; offline, the
region is shown by its code): it is used by the locks.

## What is certain (locks)

At the top of the coach, "**Do you know where you are? Tell the coach**": the
list of countries (the most likely first, from level 3); one click, and the line becomes "Certain: 🇨🇿 Czechia
(you) ✕", then Region and City are chosen the same way. What is certain (the "lock") narrows down the next search:
places and namesakes of the country, villages of the region, map zones and Plonk It tips of the country. The rules:

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
  into account; the banner says whether it confirms it ("your marks confirm it") or contradicts it ("⚠ Your marks
  prove something else"), and likewise for StreetCLIP and the AI. That is what reveals a wrong choice.
  Strong contradiction (another "certain" country, or an alphabet that excludes your country): alert at the top and
  two one-click ways out, "Switch to 🇵🇱 Poland" or "① is misread: remove it" (the mistake may come from you or from
  the reading); the coach never changes your choice itself. Your choice only narrows down what follows: namesakes
  kept for the position, region, suggested city;
- a coach lock is only named at the help level that reveals it (country at level 3, region and city at 4); below
  that, the banner says "the coach is sure of it (hidden at this help level)";
- locks **last one capture**: a new capture starts from scratch (a stale lock would skew the next round). In debug
  mode, each lock and each rejection is logged in `capture-<id>.json`.

Settings › What is certain (`[locks]`): activation, country and region set by the coach on its own,
suggested city, radius.


## Metas

A meta is a visual clue attached to one or more countries. Level 1 picks the **categories that best separate the
likely countries**, weighted by their probabilities: a category that tells the two favourites apart comes before
one that tells two outsiders apart.

Sources, from highest to lowest priority:
1. **Your metas**: `~/.config/geonesclick/my-metas.toml`, shown as "(your meta)";
2. **The seed** (`metas_amorce.toml`): about fifty well-established facts (alphabets, driving side, colour of the
   centre line, domains), written without a verified source, shown as "(seed, to be checked)".

Format (categories: `language`, `driving`, `road_lines`, `poles`, `bollards`, `plates`, `signs`, `domains`, `car`,
`vegetation`, `architecture`, `other`):

```toml
[[meta]]
category = "poles"
countries = ["HU"]
hint = "Concrete poles with holes"
look = "the holes in the poles"   # optional: the spoiler-free instruction
verified = true
```

Before revealing the countries, the coach shows for each category **what to observe** ("Look at the colour of the
centre line."), without naming a country: it is the `look` field of the metas, or failing that an instruction
specific to the category.

An error in this file is reported in the Settings screen, without blocking the coach.

**Check the seed while playing.** Each seed clue has a stable id (`id` in `metas_amorce.toml`) and its text in each
language (catalogs: `seed.<id>.hint`, `seed.<id>.look`). Each seed clue shown carries two buttons: **Right** adds a
verified copy of it to `my-metas.toml` (`seed = "<id>"`: it becomes "your meta, verified", shown in your language),
**Wrong** dismisses it (`[[rejected]]` block with `seed = "<id>"`). The verdicts are appended at the end of the file,
without touching the rest: your comments are kept. To undo, delete the block.

## Plonk It guides

The coach collects the [Plonk It](https://www.plonkit.net) guides **on your machine, for your own use**: the
database is never redistributed or versioned, each installation builds its own. Polite collection: one page at a
time, a 2 s pause (plus a random delay), immediate stop if the site answers 429, and the way Plonk It itself points
to (the `__PRELOADED_DATA__` block of the pages; their API only serves the beginner's guide). The site's
`robots.txt` allows access (`Allow: /`) and only forbids AI training, which the coach does not do.

- **First start**: built in the background: about 3 min to collect the 84 guides (4,060 tips), then their comparison
  with the view is prepared (6 s with an NVIDIA card, about 5 min on a 4-core processor; see
  [benchmarks](benchmarks.md#response-times)). The coach works without them in the meantime and shows the progress.
- **Afterwards**: one request on the list of guides at most every `refresh_days` days (30 by default), and only the
  modified guides are reloaded. "Update now" button in the Settings.
- **Storage**: `~/.local/share/geonesclick/plonkit/` (raw pages + `plonkit.sqlite`: tips, FTS5 full-text search,
  cached CLIP vectors).
- **From level 3**, when the countries are revealed: for each candidate, the Plonk It tips ranked by similarity with
  the image, with a link to the guide. It is **a lead to check**: the comparison captures the general look of the
  view, not necessarily a precise element (see the search-engine measurements below).
- Each tip is filed in a metas category by its Plonk It tags (30 %), then by keywords (`[plonkit] keywords`, 45 %),
  then by the AI for the rest (`ai_classify`, can be turned off): in batches of 25, only once per text (cache), and
  only the 12 known categories are accepted. Measured: 1,009 tips classified in 2 min 40; 92 % of the
  tips have a category; about 8 out of 10 are right on a sample, the errors mostly involving the Google camera.

- **Translation**: the guides are in English. The displayed tips are translated on demand into the coach's
  language (`[coach] language`, `en` by default = no translation), by the NVIDIA model, with a GeoGuessr
  glossary for the target language (bollard → borne, road line → marquage au sol in French…). The English shows
  first; the translations arrive in batches of 3 sent in parallel (~10 s per batch with Nemotron 3.5 Super VL),
  then are cached: a tip already read shows translated immediately. "Show the original" lets you compare. Can be
  turned off (`[plonkit] translate`); model configurable (`[plonkit] ai_model`). In practice, on demand is not
  enough: 31 tips out of 4,060 were cached, and a round waited more than 2 min for a batch that never came back.
  Hence:
  - **ahead-of-time translation** of the whole database, in the background, in batches of 10, always after the
    running rounds; it resumes where the cache stops (`[plonkit] pretranslate`, progress in Settings › Clues);
  - **a short timeout** per displayed batch (`[plonkit] translate_timeout_s`, 30 s, no retry): past this timeout,
    or if the model forgets a tip, it stays in English and the coach says so, instead of waiting.
  In debug mode, each batch (duration, tips returned, error) is noted in the round's log.

Manual command: `cd engine && .venv/bin/python -m geonesclick.plonkit collect`.

**Which search engine?** Measured on the 4,060 tips (`spikes/search_bench.py`): an in-memory dictionary, SQLite FTS5
and Tantivy all answer in less than a millisecond (StreetCLIP: 60 ms with an NVIDIA card); Elasticsearch or
Meilisearch would only add one more server. Finding the country by searching the tips for the text of the level 2
sheet fails with every engine (mean rank ~50th out of 84); comparing the image with the tips (CLIP vectors) ranks the
right country 1st or 2nd 4 times out of 5, but does not improve StreetCLIP once merged (same model, redundant
signal). Hence SQLite + vectors, without a dedicated engine.

Observed limit: if StreetCLIP ranks the right country too low (Serbia at 3 %, below the 5 % threshold), no meta can
catch it up. The next levers are independent of StreetCLIP: the visible text and closed questions asked at level 2.

## Map

The window has three tabs, at the bottom: **Coach**, **Map** and **Settings**; the help levels stay at the
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
  ("1. 🇸🇪 Sweden · ~450 × 450 km · 50 % of the positions"). It is a lead, not a proof.

On the 25 rounds of the test set whose true place is known, with the right country followed, the true place is in a
drawn zone 11 times and within 100 km of one 15 times; the zones of that country cover a median 79,000 km² (a square
about 280 km wide); 3 countries get no zone, and 3 misses exceed 800 km (see
[Measurements](benchmarks.md#what-the-map-shows)).

The map frames the zones on its own, or the likely countries while the zones are not ready; at level 4, strong proof
narrows it to its country. If the window is maximised, the map takes the full width.

**Map background and privacy.** The background comes from the **online OpenStreetMap** tiles, darkened by a CSS
filter for the coach's theme. The tile server therefore sees your IP address and the areas displayed, roughly the
place of the round. The coach follows OpenStreetMap's
[usage policy](https://operations.osmfoundation.org/policies/tiles/): app-specific User-Agent (with the project's
address),
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

The parts of the app and how they talk to each other: [architecture.md](architecture.md).
