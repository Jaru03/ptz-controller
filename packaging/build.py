"""Construye el ejecutable autocontenido de ptz-controller.

    uv run --group build python packaging/build.py

Deja el binario en ``dist/`` (``ptz-controller`` en Linux,
``ptz-controller.exe`` en Windows). Debe ejecutarse en la plataforma de
destino: PyInstaller no hace compilación cruzada.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"
SPEC_PATH = PACKAGING_DIR / "ptz-controller.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def executable_path() -> Path:
    """Ruta del binario resultante en esta plataforma."""
    name = "ptz-controller.exe" if sys.platform == "win32" else "ptz-controller"
    return DIST_DIR / name


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Borra dist/ y build/ antes de construir",
    )
    parser.add_argument(
        "--skip-icons",
        action="store_true",
        help="No regenerar los iconos a partir de icon.svg",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        import PyInstaller  # noqa: F401 - solo se comprueba que está instalado
    except ImportError:
        print(
            "Falta PyInstaller. Instálelo con:\n"
            "    uv sync --group build",
            file=sys.stderr,
        )
        return 1

    if not args.skip_icons:
        result = subprocess.run(
            [sys.executable, str(PACKAGING_DIR / "make_icons.py")],
            check=False,
        )
        if result.returncode != 0:
            print("No se pudieron generar los iconos", file=sys.stderr)
            return result.returncode

    if args.clean:
        for directory in (DIST_DIR, BUILD_DIR):
            shutil.rmtree(directory, ignore_errors=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        str(SPEC_PATH),
    ]
    print("Construyendo:", " ".join(command))
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        return result.returncode

    binary = executable_path()
    if not binary.is_file():
        print(f"PyInstaller terminó pero no se generó {binary}", file=sys.stderr)
        return 1

    size_mb = binary.stat().st_size / (1024 * 1024)
    print(f"\nEjecutable listo: {binary} ({size_mb:.0f} MB)")
    if sys.platform != "win32":
        print("Instálelo para el usuario actual con:  ./packaging/install.sh")
    else:
        print("Instálelo para el usuario actual con:  packaging\\install.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
