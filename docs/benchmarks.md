[← README](../README.md)

# Measurements and benchmarks

Each technical choice is measured on the test set before entering the coach. This page keeps the measurements
and the decisions they led to.

## Status

**End-to-end skeleton** ✅ (2026-11-07): shortcut → capture → level 1 locally → level 2 remotely, shown in the
coach window.

| Step | Measured |
|---|---|
| Shortcut → capture | about 0.3 s, GNOME notification with thumbnail and sound |
| Level 1: local StreetCLIP (RTX 3050 Ti) | about 60 ms warm, 846 MB of video memory |
| Level 2: Nemotron 3.5 Super VL (NVIDIA), no reasoning | 3 to 5 s usually, up to 15 s depending on load |
| Map: local PLONK cloud, in the background | about 0.8 s for 512 points, 119 MB of extra video memory |

## Roadmap

1. Grow the test set (20 to 30 captures through "Where was it?", with urban views for the text).
2. Measure the visible text (transcription by level 2, domains, dialling codes) and closed questions.
3. Automatic detection of the Street View view: **postponed**: cropping brings no measurable gain (see Measurements).
4. Map: outline of the region read by the AI (Natural Earth region outlines, names in several languages), and the
   exact place clicked on the map in "Where was it?" to measure the distances in km.

## Measurements

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
version of the PLONK code (see [How it works › Map](how-it-works.md#map)), checked identical to the bench: same points, same cloud centre, at 50
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
- English prompts (2026-11-12, `spikes/prompt_bench.py`, Nemotron 3.5 Super VL): the French prompts of 0.1 against
  their English rewrite, answers in English and in French. On 12 mark crops read by eye (3 runs each), the first
  English draft dropped the accents (BÉARN → BEARN, HÔTEL → HOTEL); with one sentence asking to keep every accent and
  special letter, 111 words exact out of 115 against 113 for the French prompt (5 runs on the hard cases). On whole
  views, the driving side is found more often (25/25 against 20/25), and a small, unreadable Bulgarian sign makes all
  three prompts invent a proof now and then (3 false conclusions out of 5 with the French prompt, 4 with English
  answers, 0 with French answers): an AI reading alone stays "to be confirmed", never "certain". No prompt admits an
  unreadable crop: they all make text up on it.
- On the NVIDIA free tier, availability varies: on 2026-11-07, `z-ai/glm-5.3-flash` and
  `meta/llama-3.2-90b-vision-instruct` did not answer; Nemotron Nano Omni answered in 5 s but made up details.
  Hence Nemotron 3.5 Super VL as the default.
- Screen sharing can be stopped from the GNOME indicator: the coach reports it and offers "Restart sharing".
- A third-party `gsettings` (Linuxbrew) may not write to the GNOME settings: the script explicitly calls
  `/usr/bin/gsettings`.

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
| `prompt_bench.py` | vision and marks prompts compared: words read, false conclusions, driving side | `.venv/bin/python spikes/prompt_bench.py [--repeats 3] [--only …]` |
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

## Tests

```bash
cd engine && .venv/bin/python -m pytest -q
```

They cover the configuration, cropping and masks, the vision model's answer, the metas and the tie-break, the test
set and the progress, the marks (crop, enlargement, numbering), the settings (allow list, atomic write), and the
server's access rules (origins, Host, CORS preflight, path traversal).
