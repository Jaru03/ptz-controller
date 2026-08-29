# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para el ejecutable de ptz-controller.

Se construye con ``uv run python packaging/build.py`` (que resuelve las
rutas y llama a PyInstaller con este archivo). Genera un único binario
sin consola: en Linux ``dist/ptz-controller`` y en Windows
``dist/ptz-controller.exe``.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"
IS_WINDOWS = sys.platform == "win32"


def _wsdl_dir() -> Path:
    """Directorio con los WSDL de onvif-zeep, que hay que empaquetar.

    Sin ellos el cliente zeep no puede construirse y la conexión ONVIF
    falla. onvif-zeep los instala fuera del paquete, en la raíz de
    site-packages, así que PyInstaller no los recoge solo.
    """
    import onvif

    site_packages = Path(onvif.__file__).resolve().parent.parent
    candidate = site_packages / "wsdl"
    if candidate.is_dir():
        return candidate
    for python_dir in sorted((site_packages.parent.parent).iterdir()):
        nested = python_dir / "site-packages" / "wsdl"
        if nested.is_dir():
            return nested
    raise SystemExit(
        "No se encuentra el directorio 'wsdl' de onvif-zeep; "
        "ejecute 'uv sync' antes de construir."
    )


datas = [
    (str(_wsdl_dir()), "wsdl"),
    (str(PROJECT_ROOT / "config.yaml.example"), "."),
    # pyproject.toml se empaqueta para leer la versión en la pestaña de
    # actualizaciones también en el ejecutable (models/version.py).
    (str(PROJECT_ROOT / "pyproject.toml"), "."),
    (str(PACKAGING_DIR / "icon.png"), "."),
]
# zeep lee sus XSD/XML de plantilla en tiempo de ejecución.
datas += collect_data_files("zeep")

_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if _frontend_dist.is_dir():
    # Build estático de React/Vite que carga pywebview (utils/paths.py:
    # frontend_index_html()). Hay que generarlo antes de empaquetar con
    # ``cd frontend && npm ci && npm run build``.
    datas.append((str(_frontend_dist), "frontend/dist"))

hiddenimports = [
    "onvif",
    "zeep",
    "zeep.transports",
    # onvif-zeep resuelve los servicios por nombre en tiempo de ejecución.
    *collect_submodules("onvif"),
    # Backend GTK de pywebview en Linux (en Windows usa Edge WebView2 vía
    # su propio backend, sin necesitar esto).
    *collect_submodules("webview"),
]

excludes = [
    # Módulos que ninguna dependencia usa en tiempo de ejecución, pero que
    # PyInstaller a veces detecta igual: recortan el binario.
    "matplotlib",
    "tkinter",
    "pytest",
]

analysis = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="ptz-controller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # Sin consola: es una aplicación gráfica. Los mensajes siguen yendo
    # al archivo de logs (utils/logger.py).
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PACKAGING_DIR / ("icon.ico" if IS_WINDOWS else "icon.png")),
)
