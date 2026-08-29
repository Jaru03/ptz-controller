"""Rutas de la aplicación: recursos, configuración y datos del usuario.

Un ejecutable congelado (PyInstaller) no puede tratar el directorio del
programa como escribible: en Linux acaba en ``~/.local/bin`` y en Windows
en ``Program Files``. Este módulo centraliza esa decisión para que el
resto del código no tenga que saber si se está ejecutando desde el
código fuente o desde un binario:

  * ejecutando desde el repositorio -> todo junto al proyecto, como
    siempre (``config.yaml`` y ``logs/`` en la raíz);
  * ejecutable congelado -> configuración y logs en el directorio del
    usuario, y los recursos empaquetados en ``sys._MEIPASS``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ptz-controller"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """Indica si se está ejecutando desde un ejecutable empaquetado."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Directorio de los recursos de solo lectura que acompañan al programa.

    En un ejecutable de PyInstaller es el directorio temporal donde se
    extrae el paquete (``sys._MEIPASS``); si no, la raíz del proyecto.
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir)
    return PROJECT_ROOT


def user_data_dir() -> Path:
    """Directorio escribible del usuario para configuración y logs.

    Respeta ``XDG_CONFIG_HOME`` en Linux y ``APPDATA`` en Windows. Solo
    se usa en modo congelado: desde el código fuente todo sigue viviendo
    junto al proyecto para no cambiar el flujo de desarrollo.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP_NAME


def default_config_path() -> Path:
    """Ruta del ``config.yaml`` que se usa si no se indica ``--config``."""
    if is_frozen():
        return user_data_dir() / "config.yaml"
    return PROJECT_ROOT / "config.yaml"


def default_log_dir(configured: str | os.PathLike[str] = "logs") -> Path:
    """Resuelve el directorio de logs de la configuración.

    Una ruta absoluta se respeta siempre. Una relativa cuelga del
    proyecto en desarrollo y del directorio del usuario en un ejecutable,
    donde el directorio del programa puede ser de solo lectura.
    """
    configured = Path(configured)
    if configured.is_absolute():
        return configured
    if is_frozen():
        return user_data_dir() / configured
    return PROJECT_ROOT / configured


def bundled_file(*parts: str) -> Path | None:
    """Devuelve un recurso empaquetado si existe (None si falta)."""
    candidate = resource_dir().joinpath(*parts)
    return candidate if candidate.is_file() else None


def frontend_index_html() -> Path:
    """Ruta al ``index.html`` del frontend (React/Vite) que carga pywebview.

    En desarrollo hay que generarlo antes con ``cd frontend && npm run
    build``; en el ejecutable congelado, PyInstaller lo copia dentro del
    paquete (ver ``packaging/ptz-controller.spec``). Una sola expresión
    sirve para ambos casos, igual que ``bundled_file``.
    """
    return resource_dir() / "frontend" / "dist" / "index.html"
