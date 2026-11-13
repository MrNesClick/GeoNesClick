[← README](../README.md)

# Measurements and benchmarks

Each technical choice is measured on the test set before entering the coach. This page gives the measurements and
what they decided, then the benches that produce them.

## Machines

Two machines, named in each measurement:

| Name | Hardware | System |
|---|---|---|
| **NVIDIA laptop** | Intel Core i7-12700H, NVIDIA RTX 3050 Ti Laptop GPU (4 GB) | Ubuntu 24.04, GNOME 46 |
| **Processor VM** | a virtual machine on that laptop (QEMU/KVM): 4 virtual cores, 8 GB of RAM, no GPU | fresh Ubuntu 24.04.5, GNOME 46 |

Unless a measurement says otherwise, it was taken on the NVIDIA laptop. The VM gives the times of a machine without
an NVIDIA card, and they match a physical processor with as many cores: on the laptop's own processor (GPU unused),
StreetCLIP takes 1.55 s with 4 threads, against 1.6 s in the VM, and 1.26 s with all its 14 threads.

## Response times

| Step | NVIDIA laptop | Processor VM |
|---|---|---|
| Shortcut → capture (GNOME notification with thumbnail and sound) | about 0.3 s | 0.33 s |
| Level 1: local StreetCLIP, warm | about 60 ms, 846 MB of video memory | about 1.6 s |
| Plonk It tips prepared for the comparison with the view (first launch, 4,054 tips) | 6.4 s | about 5 min, in the background |
| Map: local PLONK cloud, in the background | about 0.8 s for 512 points, 119 MB of extra video memory | not measured |
| Engine memory, StreetCLIP and the Plonk It tips loaded | — | 2.5 GB of RAM |

Level 2 runs on NVIDIA's servers, whatever the machine: Nemotron 3.5 Super VL, no reasoning, answers in 3 to 5 s
usually, up to 15 s depending on load.

## Test set

`engine/dataset/labels.toml`: 30 rounds of the classic game on the World map, 24 countries on every continent (United
States 4, France and Indonesia 2), 5 captured in a 1920×1200 browser window, 25 in a 3840×2160 one. The 25 of the
second batch hold the coordinates of the true place, read from the game, hence a true distance in km; the 5 others,
only the country and a zone in words. The images stay local (not versioned).

## StreetCLIP over several crops

Does averaging StreetCLIP over several crops (whole image, left, centre, right) help? Measured on the 30 captures
(`spikes/streetclip_tta.py`): no. Top-1 25/30 for the whole image against 24/30 for the mean, top-3 27/30 against
28/30, mean probability of the right country down (69 % → 64 %). Not kept.

## PLONK for the map

[PLONK](https://github.com/nicolas-dufour/plonk) (CVPR 2025, MIT) samples a cloud of GPS points from StreetCLIP's
vector. Measured on the 30 captures (`spikes/plonk_bench.py`, 512 points); distance to the true place on the 25 that
hold its coordinates:

| | Right country 1st | In the top 3 | Cloud centre → true place (median) | Same, when PLONK's country is right (14) |
|---|---|---|---|---|
| StreetCLIP | **25/30** | **27/30** | — | — |
| PLONK, 50 steps | 17/30 | 24/30 | 483 km | 268 km (85 to 6,195 km: Indonesia) |

- **To pick the country, it brings nothing**: it reads the same vector as StreetCLIP and does worse (17/30 against
  25/30).
- **The spread of the cloud does not tell whether the view can be located**: a tight cloud can be far off (82 km
  of spread in Brazil, 2,301 km from the place; 201 km in the United States, 7,195 km away). The true place is
  within the spread around the cloud centre for 6 of the 25 captures.
- **What it brings is the map**, once the country is known: see [What the map shows](#what-the-map-shows).
- **Cost**: 119 MB of extra video memory (peak at 987 MB with StreetCLIP); no extra image pass (same `[CLS]` token
  as StreetCLIP, cosine 0.99998 between our fp16 and the training fp32); 3.8 s for 512 points in 250 steps, 0.76 s
  in 50 steps.
- Up to 16 % of the points fall at sea (coasts, borders at 1:50m).
- **How many steps?** Same starting draw, 512 points:

  | Steps | Time | Mean distance from the cloud centre to the one at 250 steps | Cloud centre → true place (median) |
  |---|---|---|---|
  | 250 (paper default) | 3.8 s | — | 561 km |
  | 100 | 1.5 s | 33 km | 574 km |
  | **50 (kept)** | **0.76 s** | **36 km** | **483 km** |
  | 25 | 0.38 s | 58 km | 521 km |

  The countries ranked are the same at every step count. Up to 50 steps, the difference is sampling noise,
  negligible next to the distance to the true place; at 25 steps, the cloud starts to drift. Time follows the
  number of steps more than the number of points: 128 points at 50 steps take 0.29 s.

Hence **PLONK serves the map, not the choice of country**: cloud computed in the background after StreetCLIP
(50 steps, 512 points by default), filtered by the proof, can be turned off. The engine bundles a reduced version of
the PLONK code (see [How it works › Map](how-it-works.md#map)), checked identical to the bench: same points, same
cloud centre, at 50 as at 250 steps.

## What the map shows

The zones drawn by the coach, measured with the engine's own code (`spikes/map_bench.py`: same cloud, same borders,
same zones) on the 25 captures that hold the coordinates of the true place, in the two cases of the map:

| Zones drawn | True place inside | Within 100 km | Median distance | Median area of the zones | Country without zone |
|---|---|---|---|---|---|
| Right country followed (proven or read) | 11/25 | 15/25 | 18 km | 79,000 km² (a square ~280 km wide) | 3/25 |
| No country followed: all the zones | 11/25 | 15/25 | 36 km | 213,000 km² (~460 km) | 0/25 |

Following the country keeps the same hits on a zone 2.7 times smaller. The misses are large: in 3 of the 25, the
zones of the right country are more than 800 km from the place (Indonesia twice, Russia). The map is a lead toward a
region, right about 6 times out of 10.

## Cropping and masking the game's UI

Measured on the 30 captures (`spikes/compare_views.py --no-vision`):

| Variant | Right country 1st | In the top 3 | Mean probability |
|---|---|---|---|
| Whole browser window | 25/30 | 27/30 | 69 % |
| Cropped view | 24/30 | 29/30 | 71 % |
| Cropped view and masked UI | 25/30 | 29/30 | 69 % |

Capturing the **window** (not the screen) is enough: no clear gain from cropping or masking (one round more in the top
3, one less in first place). On the 5 captures measured with the vision model, it copied no country name from the
game's mini-map. Cropping and masks stay available in the configuration.

## Vision model prompts

- Making the prompt longer degrades text reading: on the "Repkény utca" sign, 8 exact readings out of 10 with the
  current prompt, 4 out of 12 with extra instructions (ignore the game's UI, write "unreadable"). The UI text is
  therefore filtered by the coach, not by the prompt.
- English prompts (`spikes/prompt_bench.py`, Nemotron 3.5 Super VL) against the French prompts of 0.1, answers in
  English and in French. On 12 mark crops read by eye (3 runs each), the first English draft dropped the accents
  (BÉARN → BEARN, HÔTEL → HOTEL); with one sentence asking to keep every accent and special letter, 111 words exact
  out of 115 against 113 for the French prompt (5 runs on the hard cases). On whole views, the driving side is found
  more often (25/25 against 20/25), and a small, unreadable Bulgarian sign makes all three prompts invent a proof now
  and then (3 false conclusions out of 5 with the French prompt, 4 with English answers, 0 with French answers): an
  AI reading alone stays "to be confirmed", never "certain". No prompt admits an unreadable crop: they all make text
  up on it.

## NVIDIA models

On the NVIDIA free tier, availability varies: `z-ai/glm-5.3-flash` and `meta/llama-3.2-90b-vision-instruct` did not
answer; Nemotron Nano Omni answered in 5 s but made up details. Hence Nemotron 3.5 Super VL as the default.

## Benches

The `spikes/` benches read the copy of the test set versioned in the repository (`engine/dataset/`); the coach saves
the new rounds in `~/.local/share/geonesclick/dataset/`. The benches are in `engine/spikes/` and run from `engine/`:

| Bench | Measures | Command |
|---|---|---|
| `streetclip_bench.py` | video memory, latency and top 5 of StreetCLIP | `.venv/bin/python spikes/streetclip_bench.py [image.png]` |
| `vlm_probe.py` | answer and latency of an NVIDIA vision model | `.venv/bin/python spikes/vlm_probe.py [--model ID] image.png` |
| `compare_views.py` | whole window, cropped view, masked UI | `.venv/bin/python spikes/compare_views.py [--no-vision]` |
| `streetclip_tta.py` | mean over several crops | `.venv/bin/python spikes/streetclip_tta.py` |
| `search_bench.py` | search engines on the Plonk It tips | `uv run --with tantivy==0.26.2 python spikes/search_bench.py` |
| `plonk_bench.py` | PLONK GPS cloud, countries, spread, distance to the true place, cost | see below |
| `map_bench.py` | zones drawn on the coach's map against the true place | `.venv/bin/python spikes/map_bench.py` |
| `prompt_bench.py` | vision and marks prompts compared: words read, false conclusions, driving side | `.venv/bin/python spikes/prompt_bench.py [--repeats 3] [--only …]` |
| `geonesclick.bench` | marks rules replayed on your rounds: false certainties, region, km | `.venv/bin/python -m geonesclick.bench [--json]` |

**Marks replay bench** (`python -m geonesclick.bench`, from `engine/`). The local rules are tuned on the whole set,
not case by case on the last round (a rule written for a Russian sign broke a Danish sign). On each "Where was it?",
the coach keeps in `~/.local/share/geonesclick/dataset/rounds/<id>.json` the text of your marks and what it had
concluded; if you paste the Google Maps link of the true place (the game's end screen), it reads its coordinates
(without ever opening it) and derives the country and region from it. The bench replays all these rounds under the
CURRENT rules (same code as the engine, local index, no network) and counts: certain country right / wrong, very
likely, region right / wrong, position error in km, and whether the true place is within the announced radius. A
rule or a threshold only changes if the bench improves without breaking a round that worked; the target is **zero
false certainty**. `--json` to compare two versions.

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
