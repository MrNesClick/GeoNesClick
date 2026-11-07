"""Prépare ce que l'AppImage embarque pour installer le moteur au premier lancement (appelé par build-appimage.sh).

Écrit dans le dossier donné :
- requirements-cuda.txt / requirements-cpu.txt : dépendances figées AVEC empreintes (uv export ; la variante CPU
  remplace PyTorch CUDA et ses bibliothèques NVIDIA par PyTorch CPU, empreinte relevée sur download.pytorch.org) ;
- packages-cuda.json / packages-cpu.json : la liste détaillée affichée par l'assistant (nom, version, taille du
  téléchargement, licence) ;
- downloads.json : la liste des téléchargements (downloads.toml), pour l'assistant écrit en Rust.

Transparence décidée avec l'utilisateur le 2026-11-07 : tout ce qui est téléchargé est montré avant le moindre octet.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import urllib.request
from importlib import metadata
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "engine"
CUDA_ONLY = re.compile(r"^(nvidia-|triton$|cuda-)")  # paquets de la seule variante CUDA
LOCAL_BUILT = ("pygobject", "pycairo")  # compilés par build-appimage.sh, livrés en wheel dans l'AppImage
CPU_INDEX = "https://download.pytorch.org/whl/cpu/torch/"


def export_requirements() -> str:
    args = ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header"]
    for name in LOCAL_BUILT:
        args += ["--no-emit-package", name]
    return subprocess.run(args, cwd=ENGINE, check=True, capture_output=True, text=True).stdout


def blocks(text: str) -> list[tuple[str, str]]:
    """(nom, bloc de lignes) pour chaque paquet d'un export uv (une ligne + ses « --hash » en suite)."""
    out, current = [], []
    for line in text.splitlines():
        if line and not line.startswith((" ", "#")):
            if current:
                out.append(current)
            current = [line]
        elif current and line.strip():
            current.append(line)
    if current:
        out.append(current)
    return [(re.split(r"[=<>; \[]", b[0], maxsplit=1)[0].lower(), "\n".join(b)) for b in out]


def cpu_torch_line(version: str) -> str:
    """Ligne figée de PyTorch CPU, avec l'empreinte publiée par l'index PyTorch (vérifiée par uv à l'installation)."""
    with urllib.request.urlopen(CPU_INDEX, timeout=60) as resp:  # noqa: S310 (adresse fixe, https)
        page = resp.read().decode()
    wheel = f"torch-{version}%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl"
    found = re.search(re.escape(wheel) + r"#sha256=([0-9a-f]{64})", page)
    if not found:
        sys.exit(f"PyTorch CPU {version} introuvable sur {CPU_INDEX}")
    return f"torch=={version}+cpu \\\n    --hash=sha256:{found.group(1)}"


def wheel_sizes() -> dict[str, tuple[str, int]]:
    """Taille du téléchargement de chaque paquet (wheel Linux x86_64, Python 3.12), d'après uv.lock."""
    lock = tomllib.loads((ENGINE / "uv.lock").read_text())
    out = {}
    for p in lock["package"]:
        wheels = [w for w in p.get("wheels", [])
                  if ("manylinux" in w["url"] and "x86_64" in w["url"]) or "none-any" in w["url"]]
        wheels = [w for w in wheels if any(t in w["url"] for t in ("cp312", "abi3", "py3-none", "py2.py3"))]
        out[p["name"].lower()] = (p["version"], max((w.get("size", 0) for w in wheels), default=0))
    return out


def license_of(name: str) -> str:
    """Licence déclarée par le paquet installé dans le venv de développement (même version que l'AppImage)."""
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "?"
    if expr := meta.get("License-Expression"):
        return expr
    classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return ", ".join(classifiers)
    text = (meta.get("License") or "").strip().splitlines()
    return text[0][:60] if text else "?"


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    exported = blocks(export_requirements())
    sizes = wheel_sizes()
    torch_version = sizes["torch"][0]
    cuda = [b for _, b in exported]
    cpu = [b for name, b in exported if not CUDA_ONLY.match(name) and name != "torch"] + [cpu_torch_line(torch_version)]
    (out / "requirements-cuda.txt").write_text("\n".join(cuda) + "\n")
    (out / "requirements-cpu.txt").write_text("\n".join(cpu) + "\n")
    for variant, names in (("cuda", [n for n, _ in exported]),
                           ("cpu", [n for n, _ in exported if not CUDA_ONLY.match(n)])):
        rows = [{"name": n, "version": sizes.get(n, ("?", 0))[0], "size": sizes.get(n, ("?", 0))[1],
                 "license": license_of(n)} for n in names]
        if variant == "cpu":
            torch = next(r for r in rows if r["name"] == "torch")
            torch.update(version=f"{torch_version}+cpu", size=0, note="taille publiée par download.pytorch.org")
        (out / f"packages-{variant}.json").write_text(json.dumps(sorted(rows, key=lambda r: -r["size"]),
                                                                 ensure_ascii=False, indent=1))
    manifest = tomllib.loads((ENGINE / "src" / "geonesclick" / "downloads.toml").read_text())
    (out / "downloads.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"{len(cuda)} paquets (CUDA), {len(cpu)} (CPU) ; liste des téléchargements prête dans {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
