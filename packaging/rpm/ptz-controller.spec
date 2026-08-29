# Receta RPM de ptz-controller para Fedora (y derivados con rpmbuild).
#
# Empaqueta el binario autocontenido de PyInstaller (que ya incluye el
# intérprete, PySide6, onvif-zeep y los WSDL), el icono y la entrada de
# menú. Como PyInstaller no hace compilación cruzada, primero hay que
# construir el binario en esta plataforma:
#
#     uv sync --group build
#     uv run --group build python packaging/build.py --clean
#
# y a continuación generar el RPM:
#
#     uv run --group build python packaging/build_rpm.py
#
# El binario resultante arranca siempre en modo cámara real (--real); el
# modo simulado queda disponible desde la acción "Modo simulado" del menú
# de aplicaciones.
#
# Nombre de archivo distinto del spec de PyInstaller: este directorio
# (packaging/rpm/) no debe confundirse con packaging/ptz-controller.spec.

%global debug_package %{nil}
%global _buildwithdebuginfo 0
%undefine __brp_mangle_shebangs

Name:           ptz-controller
Version:        0.1.0
Release:        1%{?dist}
Summary:        Controlador universal de cámaras PTZ ONVIF

# Ajustar a la licencia real del proyecto cuando se declare en el repo.
License:        MIT
URL:            https://github.com/Jaru03/ptz-controller
Source0:        %{name}-%{version}.tar.gz

# El binario PyInstaller está ligado a la arquitectura de compilación.
BuildArch:      x86_64

# Bibliotecas de sistema que PySide6/OpenCV esperan en el arranque; el
# resto (Qt, libav, zeep) viaja dentro del binario.
Requires:       libxkbcommon%{?_isa}
Requires:       fontconfig%{?_isa}
Requires:       dbus-libs%{?_isa}
Requires:       mesa-libGL%{?_isa}
Requires:       mesa-libEGL%{?_isa}

# Backend GTK de pywebview, para el modo --web-gui (opcional mientras la
# GUI PySide6 siga siendo la que arranca por defecto). PyInstaller no
# empaqueta bibliotecas de sistema de GTK/WebKit, así que hacen falta
# instaladas en la máquina del usuario. Nombres verificados en Fedora.
Requires:       webkit2gtk4.1%{?_isa}
Requires:       python3-gobject%{?_isa}

%description
Controlador de cámaras PTZ compatibles con ONVIF: teclado (WASD) y mando
SDL, movimiento proporcional, presets y una interfaz PySide6 con vista
previa RTSP. Incluye un modo simulado (Mock) para probar sin hardware.

Este paquete instala el ejecutable autocontenido (PyInstaller) y lo
arranca en modo cámara real por defecto.

%prep
%setup -q -n %{name}-%{version}

%build
# El binario ya viene construido por PyInstaller: no hay etapa de compilación.

%install
install -Dm755 ./ptz-controller %{buildroot}%{_bindir}/%{name}
install -Dm644 ./ptz-controller.desktop %{buildroot}%{_datadir}/applications/%{name}.desktop
install -Dm644 ./icon.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/%{name}.png

%post
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || :
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -qtf %{_datadir}/icons/hicolor >/dev/null 2>&1 || :
fi

%files
%{_bindir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/256x256/apps/%{name}.png

%changelog
* Mon Aug 03 2026 Jose Rico <josearudeveloper@gmail.com> - 0.1.0-1
- Paquete RPM inicial con el ejecutable PyInstaller en modo real.
