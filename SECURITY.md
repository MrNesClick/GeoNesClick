# Security

## Reporting a vulnerability

Please report security issues privately, through GitHub: open the repository's **Security** tab, then **Report a
vulnerability**. Do not open a public issue for them.

Say what is affected (version, component), how to reproduce it, and what an attacker could do with it. You will get
an answer within a week; once a fix is released, the advisory is published with credit to you if you wish.

## Supported versions

Only the latest release receives security fixes.

## What GeoNesClick protects

GeoNesClick runs on your machine and handles your screen captures and an API key, so these are the boundaries it
keeps (details in [docs/how-it-works.md](docs/how-it-works.md) and [docs/configuration.md](docs/configuration.md)):

- The engine listens on `127.0.0.1` only and refuses requests from any origin other than the app's window, against
  websites open in your browser and DNS rebinding.
- The NVIDIA API key is stored in `~/.config/geonesclick/nvapi.key`, readable by you only, never shown again (only
  its last 4 characters) and never sent anywhere but the configured API.
- Settings that could redirect the key, write elsewhere on the disk or run other code (server address, API address,
  folders, model sources) can only be changed in the configuration file, never from the interface.
- Every download is listed before the first byte; Python packages are pinned and checked by hash, the AI models are
  pinned to a revision and loaded from safetensors only.
- Text read from the screen, from the AI's answers or from the Plonk It guides is treated as data: never inserted as
  HTML, never run.
