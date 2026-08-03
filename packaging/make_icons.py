"""Genera los iconos PNG e ICO a partir de ``packaging/icon.svg``.

Se ejecuta desde ``packaging/build.py``; los resultados se versionan para
que construir el ejecutable no dependa de tener Qt SVG a mano.

    uv run python packaging/make_icons.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent
SVG_PATH = PACKAGING_DIR / "icon.svg"
PNG_PATH = PACKAGING_DIR / "icon.png"
ICO_PATH = PACKAGING_DIR / "icon.ico"

# Tamaños que Windows espera dentro de un .ico.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _ensure_qt_app() -> None:
    """Qt necesita una aplicación viva antes de rasterizar nada."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None:
        QGuiApplication([sys.argv[0]])


def render_png(size: int) -> bytes:
    """Renderiza el SVG a PNG del tamaño indicado usando Qt."""
    _ensure_qt_app()
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(SVG_PATH)).render(painter)
    painter.end()

    # El QByteArray debe sobrevivir al QBuffer: pasar uno temporal deja
    # un puntero colgando y Qt revienta al escribir.
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"No se pudo codificar el icono de {size} px")
    buffer.close()
    return bytes(data)


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

    images = {size: render_png(size) for size in ICO_SIZES}
    PNG_PATH.write_bytes(images[256])
    ICO_PATH.write_bytes(build_ico(images))
    print(f"Generados {PNG_PATH.name} y {ICO_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
