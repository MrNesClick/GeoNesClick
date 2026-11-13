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
```

Without `crop`, the analysed zone is the window without the browser's bars (tab titles, address, bookmarks), so they
never reach the models or the NVIDIA API. The coach finds where the page starts in two ways and cuts at the lower of
the two edges found:
- in the capture itself, below the plain line the browser draws across the whole width under its bars (Chrome);
- by comparing captures: the bars stay the same from one round to the next while the view changes, so the first row
  that changed between two captures of the same size is the page. The lowest one found is kept per window size in
  `~/.config/geonesclick/page-top.json`; this way knows nothing of the browser or its theme.

If neither finds anything, it cuts 12 % of the top (144 px in a 1200 px high window, enough for Chrome's bars) and
says so under the capture. A `crop` set by hand takes precedence.

Each kind of help can be turned off: level 2, seed, "Look…" instructions, "Right" / "Wrong" buttons, answered
country, confusions, notifications, capture copies (sections `[coach]`, `[vision]`, `[metas]`, `[dataset]`,
`[capture]` of the default file). To remove candidate countries: untick them in Settings › Analysis, or
`[streetclip] exclude_countries = ["RU", "UA"]` in the file (it can add countries to the list, but not remove any
otherwise).

**Everything is configurable**, also from the app's **Settings** tab, arranged in collapsible sections (General,
Analysis, Clues, Map, Capture, Marks, What is certain, Test set, Storage, Engine, GNOME integration), each with its
one-line summary;
the fine-grained settings are in an "Advanced" part. Each change applies and is saved right away (a checkbox, a menu,
or a field when leaving it); a refused value is flagged in place and the screen goes back to the value in effect. The
screen only writes to `config.toml` the values you change, keeping your comments and their order. Candidate
countries: untick a country to rule it out, or add one (English name and ISO code). Three settings only take effect
at the next start (StreetCLIP enabled, its device, and what GNOME offers to share): the screen says so. The GNOME
integration section is not stored in `config.toml`: it shows and changes what is in place in GNOME, the keyboard
shortcuts and the applications-menu entry (`~/.local/share/applications/fr.mrnesclick.geonesclick.desktop` and its
icon in `~/.local/share/icons/hicolor/`, which give the app its own icon in the dock). Both are offered with the
AppImage only; the entry points to the AppImage and follows it when it is opened from another place.

**The only exception is security**: these settings can only be changed in the file, then by restarting the app.
The screen shows them read-only with their reason:

| Setting | Why file-only |
|---|---|
| `[server]` host, port, allowed_origins | the engine must only listen to your machine and your coach window |
| `[vision]` base_url, api_key_env | a request could redirect your API key to another server |
| `[streetclip]` and `[plonk]` model, revision | a downloaded model runs on your machine: a trapped model could run code |
| `[map]` tile_url, attribution_url | must also be allowed in the window (CSP and Tauri permissions) |
| `[rules]` places_url, detail_url, regions_url | a source downloaded then read on your machine: it must not be diverted |
| folders and files (`[capture]` and `[dataset]` directory, `[metas]` user_file, `[plonkit]` data_dir, `[rules]` places_dir) | a request must not be able to make the engine write elsewhere on the disk |

**Debug mode** (Settings › Engine, `[debug] enabled`, off by default): next to each capture, the engine writes a
`capture-<id>.json` log (StreetCLIP countries, zones, what the AI read and its conclusion, timings, "Where was it?"
label), to replay a round afterwards. Local, deleted with the old captures.

A test checks that each configuration key is either editable on screen or in this list: a setting added without
being filed makes the tests fail. The list of NVIDIA models is public:
`curl -s https://integrate.api.nvidia.com/v1/models`.
