#!/usr/bin/env bash
# Instala ptz-controller para el usuario actual (sin privilegios de root).
#
#   ./packaging/install.sh              instala desde dist/ptz-controller
#   ./packaging/install.sh --uninstall  desinstala (conserva la configuración)
#
# Copia el ejecutable a ~/.local/bin, registra el icono y crea la entrada
# del menú de aplicaciones. La configuración y los logs los crea el propio
# programa en ~/.config/ptz-controller la primera vez que arranca.

set -euo pipefail

APP_ID="ptz-controller"
APP_NAME="Controlador PTZ ONVIF"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# El binario está junto al script cuando se descarga el paquete de la
# release, y en dist/ cuando se acaba de construir desde el código.
find_first() {
    local candidate
    for candidate in "$@"; do
        if [[ -f "${candidate}" ]]; then
            printf '%s' "${candidate}"
            return 0
        fi
    done
    return 1
}

SOURCE_BINARY="$(find_first "${SCRIPT_DIR}/${APP_ID}" "${PROJECT_ROOT}/dist/${APP_ID}" || true)"
SOURCE_ICON="$(find_first "${SCRIPT_DIR}/icon.png" "${PROJECT_ROOT}/packaging/icon.png" || true)"

BIN_DIR="${XDG_BIN_HOME:-${HOME}/.local/bin}"
DATA_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/${APP_ID}"

TARGET_BINARY="${BIN_DIR}/${APP_ID}"
TARGET_ICON="${DATA_DIR}/icons/hicolor/256x256/apps/${APP_ID}.png"
TARGET_DESKTOP="${DATA_DIR}/applications/${APP_ID}.desktop"

info() { printf '  %s\n' "$1"; }
error() { printf 'Error: %s\n' "$1" >&2; }

refresh_desktop_database() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "${DATA_DIR}/applications" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -qtf "${DATA_DIR}/icons/hicolor" >/dev/null 2>&1 || true
    fi
}

uninstall() {
    echo "Desinstalando ${APP_NAME}…"
    rm -f "${TARGET_BINARY}" "${TARGET_ICON}" "${TARGET_DESKTOP}"
    refresh_desktop_database
    info "Eliminado el ejecutable, el icono y la entrada del menú."
    if [[ -d "${CONFIG_DIR}" ]]; then
        info "Se conserva la configuración en ${CONFIG_DIR}"
        info "Bórrela a mano si no la quiere: rm -rf '${CONFIG_DIR}'"
    fi
}

install_app() {
    if [[ -z "${SOURCE_BINARY}" ]]; then
        error "No se encuentra el ejecutable '${APP_ID}'."
        error "Se ha buscado en ${SCRIPT_DIR} y en ${PROJECT_ROOT}/dist"
        error "Si trabaja desde el código, constrúyalo antes con:"
        error "    uv run --group build python packaging/build.py"
        exit 1
    fi

    echo "Instalando ${APP_NAME} para ${USER}…"

    install -Dm755 "${SOURCE_BINARY}" "${TARGET_BINARY}"
    info "Ejecutable: ${TARGET_BINARY}"

    if [[ -n "${SOURCE_ICON}" ]]; then
        install -Dm644 "${SOURCE_ICON}" "${TARGET_ICON}"
        info "Icono: ${TARGET_ICON}"
    fi

    mkdir -p "$(dirname "${TARGET_DESKTOP}")"
    cat > "${TARGET_DESKTOP}" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=${APP_NAME}
GenericName=Controlador de cámaras PTZ
Comment=Controla cámaras PTZ ONVIF con teclado o mando
Exec=${TARGET_BINARY} --real
TryExec=${TARGET_BINARY}
Icon=${APP_ID}
Terminal=false
Categories=AudioVideo;Video;Player;
Keywords=PTZ;ONVIF;cámara;camera;RTSP;
StartupNotify=true
Actions=Mock;

[Desktop Action Mock]
Name=Modo simulado (sin cámara)
Exec=${TARGET_BINARY} --mock
DESKTOP
    chmod 644 "${TARGET_DESKTOP}"
    info "Menú de aplicaciones: ${TARGET_DESKTOP}"

    refresh_desktop_database

    echo
    echo "Listo. Puede lanzarlo desde el menú de aplicaciones o con:  ${APP_ID}"
    case ":${PATH}:" in
        *":${BIN_DIR}:"*) ;;
        *)
            echo
            info "Aviso: ${BIN_DIR} no está en su PATH."
            info "Añádalo a ~/.bashrc:  export PATH=\"\${PATH}:${BIN_DIR}\""
            ;;
    esac
    echo
    info "La configuración se creará en ${CONFIG_DIR}/config.yaml"
    info "Edite ahí la IP, el usuario y la contraseña de su cámara."
    echo
    info "Nota: la interfaz web (${APP_ID} --web-gui, opcional) necesita"
    info "WebKitGTK instalado en el sistema (PyInstaller no lo empaqueta)."
    info "Debian/Ubuntu: sudo apt install gir1.2-webkit2-4.1 python3-gi"
    info "Fedora:        sudo dnf install webkit2gtk4.1 python3-gobject"
}

case "${1:-}" in
    --uninstall|-u) uninstall ;;
    --help|-h) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
    "") install_app ;;
    *) error "Opción desconocida: $1"; exit 2 ;;
esac
