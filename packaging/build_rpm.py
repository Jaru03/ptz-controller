"""Genera el RPM de ptz-controller para Fedora.

    uv run --group build python packaging/build_rpm.py

Requiere el binario ``dist/ptz-controller`` (constrúyalo antes con
``packaging/build.py``) y ``rpmbuild`` en el sistema. El RPM se deja en
``dist/rpm/RPMS/x86_64/ptz-controller-<versión>.x86_64.rpm``.

El binario ya es autocontenido (PyInstaller), así que el spec solo lo
copia a ``/usr/bin`` junto con el icono y la entrada de menú. No hay
etapa de compilación: cada RPM debe construirse en la misma arquitectura
y distribución que la del binario.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"
RPM_DIR = PACKAGING_DIR / "rpm"
SPEC_PATH = RPM_DIR / "ptz-controller.spec"
DESKTOP_PATH = RPM_DIR / "ptz-controller.desktop"
ICON_PATH = PACKAGING_DIR / "icon.png"
DIST_DIR = PROJECT_ROOT / "dist"
RPM_TOPDIR = DIST_DIR / "rpm"


def project_version() -> str:
    """Versión del proyecto desde pyproject.toml."""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def check_rpmbuild() -> None:
    if shutil.which("rpmbuild") is None:
        print(
            "No se encuentra 'rpmbuild'. En Fedora instálelo con:\n"
            "    sudo dnf install rpm-build\n"
            "y los helpers de paquetes con:\n"
            "    sudo dnf install desktop-file-utils",
            file=sys.stderr,
        )
        raise SystemExit(1)


def ensure_binary() -> Path:
    binary = DIST_DIR / "ptz-controller"
    if binary.is_file():
        return binary
    print(
        f"No se encuentra {binary}.\n"
        "Constrúyalo antes con:\n"
        "    uv sync --group build\n"
        "    uv run --group build python packaging/build.py --clean",
        file=sys.stderr,
    )
    raise SystemExit(1)


def make_source_tarball(version: str) -> Path:
    """Empaqueta el binario, la entrada de menú y el icono como Source0.

    El directorio dentro del tarball debe llamarse ``%{name}-%{version}``
    para que el ``%setup`` del spec lo extraiga con ese nombre.
    """
    sources_dir = RPM_TOPDIR / "SOURCES"
    sources_dir.mkdir(parents=True, exist_ok=True)
    tarball = sources_dir / f"ptz-controller-{version}.tar.gz"

    stage = sources_dir / "stage" / f"ptz-controller-{version}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(ensure_binary(), stage / "ptz-controller")
    shutil.copy2(DESKTOP_PATH, stage / "ptz-controller.desktop")
    shutil.copy2(ICON_PATH, stage / "icon.png")

    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(stage, arcname=f"ptz-controller-{version}")
    shutil.rmtree(stage.parent)
    return tarball


def prepare_spec(version: str) -> Path:
    """Copia el spec a SPECS y le fija la versión del proyecto."""
    specs_dir = RPM_TOPDIR / "SPECS"
    specs_dir.mkdir(parents=True, exist_ok=True)
    target = specs_dir / "ptz-controller.spec"
    content = SPEC_PATH.read_text(encoding="utf-8")
    content = content.replace(
        "\nVersion:        0.1.0\n",
        f"\nVersion:        {version}\n",
    )
    target.write_text(content, encoding="utf-8")
    return target


def run_rpmbuild(spec: Path) -> int:
    for sub in ("BUILD", "BUILDROOT", "RPMS", "SRPMS"):
        (RPM_TOPDIR / sub).mkdir(parents=True, exist_ok=True)
    command = [
        "rpmbuild",
        f"--define=_topdir {RPM_TOPDIR}",
        "-bb",
        str(spec),
    ]
    print("Construyendo RPM:", " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return result.returncode
    rpms = sorted((RPM_TOPDIR / "RPMS").rglob("*.rpm"))
    if not rpms:
        print("rpmbuild terminó pero no se generó ningún .rpm", file=sys.stderr)
        return 1
    for rpm in rpms:
        print(f"\nRPM listo: {rpm}")
        print("Instálelo en Fedora con:  sudo dnf install <ruta>")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    check_rpmbuild()
    version = project_version()
    make_source_tarball(version)
    spec = prepare_spec(version)
    return run_rpmbuild(spec)


if __name__ == "__main__":
    raise SystemExit(main())
