"""Genera los iconos PNG e ICO a partir de ``packaging/icon.svg``.

Se ejecuta desde ``packaging/build.py``; los resultados se versionan para
que construir el ejecutable no dependa de tener nada capaz de rasterizar
SVG a mano — de hecho ``build.yml`` compila siempre con ``--skip-icons``
y usa directamente los ``icon.png``/``icon.ico`` ya versionados. Este
script solo hace falta si alguien edita ``packaging/icon.svg``:

    uv run --with cairosvg python packaging/make_icons.py

``cairosvg`` no está en las dependencias del proyecto a propósito (es una
herramienta de un solo uso, no algo que necesite nadie más para
construir o ejecutar la app) — de ahí el ``--with`` en vez de añadirlo a
``pyproject.toml``.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent
SVG_PATH = PACKAGING_DIR / "icon.svg"
PNG_PATH = PACKAGING_DIR / "icon.png"
ICO_PATH = PACKAGING_DIR / "icon.ico"

# Tamaños que Windows espera dentro de un .ico.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(size: int) -> bytes:
    """Renderiza el SVG a PNG del tamaño indicado."""
    import cairosvg

    result = cairosvg.svg2png(
        url=str(SVG_PATH), output_width=size, output_height=size
    )
    assert isinstance(result, bytes)
    return result


def build_ico(images: dict[int, bytes]) -> bytes:
    """Empaqueta varios PNG en un contenedor ICO.

    Windows admite imágenes PNG dentro del .ico desde Vista, así que no
    hace falta convertirlas a BMP ni depender de Pillow.
    """
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)  # reservado, tipo icono, nº imágenes
    entries = b""
    payload = b""
    offset = len(header) + count * 16
    for size, data in sorted(images.items()):
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,  # ancho (0 significa 256)
            0 if size >= 256 else size,  # alto
            0,  # colores de la paleta
            0,  # reservado
            1,  # planos de color
            32,  # bits por píxel
            len(data),
            offset,
        )
        payload += data
        offset += len(data)
    return header + entries + payload


def main() -> int:
    if not SVG_PATH.is_file():
        print(f"No se encuentra {SVG_PATH}", file=sys.stderr)
        return 1

    try:
        images = {size: render_png(size) for size in ICO_SIZES}
    except ImportError:
        print(
            "Falta cairosvg para rasterizar el SVG. Instálelo solo para "
            "esta tarea puntual con:\n"
            "    uv run --with cairosvg python packaging/make_icons.py",
            file=sys.stderr,
        )
        return 1

    PNG_PATH.write_bytes(images[256])
    ICO_PATH.write_bytes(build_ico(images))
    print(f"Generados {PNG_PATH.name} y {ICO_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
