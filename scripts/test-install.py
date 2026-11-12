#!/usr/bin/env python3
"""Installs the engine in fresh containers of each supported distribution, as the AppImage's installer does.

    scripts/test-install.py                       # the six systems, one after the other
    scripts/test-install.py fedora archlinux      # some of them
    scripts/test-install.py --bundle DIR          # another engine bundle (default: app/src-tauri/engine-bundle)

For each system: the system components under the names of the installer's table (app/src-tauri/src/setup.rs, read
here, never copied), the engine with install-engine.sh (processor variant), then scripts/install-smoke.py (GStreamer,
Cairo, a StreetCLIP analysis). The two screen-sharing portals pull a whole GNOME desktop: their names are only checked
in the repositories. The Hugging Face cache is shared between the containers: StreetCLIP is downloaded once.
Needs Docker and an engine bundle (scripts/build-appimage.sh --engine-only).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = {  # name: (image, package manager)
    "ubuntu-24.04": ("ubuntu:24.04", "apt"),
    "ubuntu-26.04": ("ubuntu:26.04", "apt"),
    "debian-13": ("debian:13", "apt"),
    "fedora": ("fedora:45", "dnf"),
    "archlinux": ("archlinux:latest", "pacman"),
    "opensuse": ("opensuse/tumbleweed:latest", "zypper"),
}
MANAGERS = ("apt", "dnf", "pacman", "zypper")  # the order of the names in setup.rs
PORTALS = {"portal", "portal_gnome"}


def package_table() -> dict[str, dict[str, str]]:
    """{check: {package manager: package}}, from system_checks() in setup.rs."""
    source = (ROOT / "app/src-tauri/src/setup.rs").read_text(encoding="utf-8")
    body = source[source.index("fn system_checks("):]
    body = body[:body.index("\n}\n")]
    table = {}
    for check, names in re.findall(r'check\(\s*"setup\.check\.(\w+)".*?(\[[^\]]*\])', body, re.S):
        same = re.fullmatch(r'\["([^"]+)";\s*4\]', names)
        listed = re.findall(r'"([^"]+)"', names)
        values = [same.group(1)] * 4 if same else listed
        if len(values) != len(MANAGERS):
            raise SystemExit(f"setup.rs: cannot read the packages of {check}: {names}")
        table[check] = dict(zip(MANAGERS, values, strict=True))
    if len(table) != 7:
        raise SystemExit(f"setup.rs: expected 7 system checks, read {len(table)}")
    return table


def system_commands(manager: str, libraries: list[str], portals: list[str]) -> str:
    libs, names = " ".join(libraries), " ".join(portals)
    return {
        "apt": "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq"
               f" && apt-get install -y -qq --no-install-recommends ca-certificates {libs} >/dev/null"
               f" && apt-cache show {names} >/dev/null",
        "dnf": f"dnf install -y -q {libs} && dnf info -q {names} >/dev/null",
        "pacman": f"pacman -Syu --noconfirm --needed --noprogressbar {libs} >/dev/null"
                  f" && pacman -Si {names} >/dev/null",
        "zypper": f"zypper --non-interactive --quiet install {libs}"
                  + "".join(f" && zypper --non-interactive search --match-exact {p} >/dev/null" for p in portals),
    }[manager]


def run(name: str, bundle: Path, hf_cache: Path) -> tuple[bool, str]:
    image, manager = SYSTEMS[name]
    table = package_table()
    libraries = [names[manager] for check, names in table.items() if check not in PORTALS]
    portals = [names[manager] for check, names in table.items() if check in PORTALS]
    # "STEP" lines: the time of each step, to see which one is slow.
    script = ('set -e; step() { echo "STEP $(date +%s) $1"; }; step system; '
              f"{system_commands(manager, libraries, portals)}"
              " && step engine && /bundle/install-engine.sh cpu"
              " && step smoke && ~/.local/share/geonesclick/engine/venv/bin/python /smoke/install-smoke.py"
              " && step end")
    command = ["docker", "run", "--rm", "--pull", "missing",
               "-v", f"{bundle}:/bundle:ro", "-v", f"{ROOT / 'scripts'}:/smoke:ro",
               "-v", f"{hf_cache}:/root/.cache/huggingface", image, "sh", "-c", script]
    try:  # a stuck mirror must not hold a release: 15 min per system (usually 30 to 90 s)
        done = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return False, "no end after 15 min (a package mirror that does not answer?)"
    lines = done.stdout.splitlines()
    steps = [line.split(" ", 2)[1:] for line in lines if line.startswith("STEP ")]
    times = ", ".join(f"{name} {int(steps[i + 1][0]) - int(at)} s" for i, (at, name) in enumerate(steps[:-1]))
    result = next((line for line in lines if line.startswith("engine OK")), None)
    if done.returncode == 0 and result:
        return True, f"{result} ({times})"
    return False, "\n".join((done.stdout + done.stderr).strip().splitlines()[-20:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Checked by hand: argparse validates an empty nargs="*" list against `choices` differently across Python
    # versions (the default list on 3.12, [] on 3.15).
    parser.add_argument("systems", nargs="*", metavar="system", help=f"default: all of {', '.join(SYSTEMS)}")
    parser.add_argument("--bundle", type=Path, default=ROOT / "app/src-tauri/engine-bundle")
    parser.add_argument("--remove-images", action="store_true", help="remove each image after its test (CI disk)")
    args = parser.parse_args()
    unknown = [name for name in args.systems if name not in SYSTEMS]
    if unknown:
        parser.error(f"unknown system {', '.join(unknown)} (choose from {', '.join(SYSTEMS)})")
    bundle = args.bundle.resolve()
    if not (bundle / "install-engine.sh").is_file():
        raise SystemExit(f"no engine bundle in {bundle}: run scripts/build-appimage.sh --engine-only")
    failed = []
    with tempfile.TemporaryDirectory(prefix="gnc-hf-") as hf_cache:
        for name in args.systems or list(SYSTEMS):
            start = time.monotonic()
            ok, tail = run(name, bundle, Path(hf_cache))
            seconds = time.monotonic() - start
            print(f"{'ok  ' if ok else 'FAIL'} {name} ({seconds:.0f} s): {tail if ok else ''}", flush=True)
            if not ok:
                failed.append(name)
                print(tail, file=sys.stderr)
            if args.remove_images:
                subprocess.run(["docker", "rmi", SYSTEMS[name][0]], capture_output=True)
        # Files written by root in the containers: removed by a container too.
        subprocess.run(["docker", "run", "--rm", "-v", f"{hf_cache}:/c", "busybox:1.37", "sh", "-c", "rm -rf /c/*"],
                       capture_output=True)
    if failed:
        print(f"installation failed on: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
