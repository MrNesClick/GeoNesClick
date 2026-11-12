[← README](../README.md)

# Configuration

Everything is set in `~/.config/geonesclick/config.toml`, which overrides key by key the commented default values
of [`engine/src/geonesclick/default_config.toml`](../engine/src/geonesclick/default_config.toml). Example:

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
