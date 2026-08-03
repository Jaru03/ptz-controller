"""Versión de la aplicación y comprobación de actualizaciones.

La versión vive en ``pyproject.toml`` (fuente única): en desarrollo se
lee de la raíz del proyecto y en el ejecutable empaquetado, del archivo
que PyInstaller copia junto al binario (ver
``packaging/ptz-controller.spec``). La comprobación de actualizaciones
consulta la API pública de releases de GitHub y no envía ningún dato del
usuario.
"""

from __future__ import annotations

import json
import re
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass

from utils.paths import PROJECT_ROOT, bundled_file

APP_REPO = "Jaru03/ptz-controller"
RELEASES_PAGE = f"https://github.com/{APP_REPO}/releases"
_LATEST_API = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_TIMEOUT_S = 8.0


def get_version() -> str:
    """Devuelve la versión de la aplicación desde ``pyproject.toml``."""
    path = bundled_file("pyproject.toml") or PROJECT_ROOT / "pyproject.toml"
    with open(path, "rb") as fh:
        return str(tomllib.load(fh)["project"]["version"])


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Convierte ``1.2.3`` o ``v1.2.3`` en ``(1, 2, 3)``; None si no encaja."""
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def compare_versions(current: str, latest: str) -> int:
    """Compara dos versiones: -1 si ``current < latest``, 1 si es mayor, 0 iguales."""
    a = parse_version(current)
    b = parse_version(latest)
    if a is None or b is None:
        return 0 if a == b else -1
    return (a > b) - (a < b)


@dataclass
class UpdateResult:
    """Resultado de una comprobación de actualizaciones."""

    ok: bool = True
    error: str = ""
    current: str = ""
    latest: str = ""
    up_to_date: bool = True
    release_url: str = RELEASES_PAGE

    @property
    def available(self) -> bool:
        """Hay una versión más nueva disponible."""
        return self.ok and not self.up_to_date


def _latest_release_json(timeout: float = _TIMEOUT_S) -> dict:
    """Descarga la release estable más reciente de la API de GitHub."""
    request = urllib.request.Request(
        _LATEST_API,
        headers={
            "User-Agent": f"ptz-controller/{get_version()}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_updates(timeout: float = _TIMEOUT_S) -> UpdateResult:
    """Compara la versión instalada con la última release publicada."""
    current = get_version()
    try:
        payload = _latest_release_json(timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UpdateResult(
            ok=False, error=str(exc), current=current, release_url=RELEASES_PAGE
        )

    latest = str(payload.get("tag_name") or "").strip()
    html_url = str(payload.get("html_url") or RELEASES_PAGE)
    if not latest:
        return UpdateResult(
            ok=False,
            error="No se pudo leer la versión de la última release.",
            current=current,
            release_url=RELEASES_PAGE,
        )

    return UpdateResult(
        ok=True,
        current=current,
        latest=latest,
        up_to_date=compare_versions(current, latest) >= 0,
        release_url=html_url,
    )