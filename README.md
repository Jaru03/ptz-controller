# ptz-controller

Controlador universal de cámaras PTZ compatibles con ONVIF.

Permite controlar una cámara PTZ desde el **teclado** (WASD) o desde un
**mando de juego** (DualShock 4/5, DualSense, Xbox o cualquier mando SDL),
con movimiento proporcional, zona muerta, presets y una interfaz web
moderna (React + shadcn/ui, dentro de una ventana nativa con pywebview)
con vista previa RTSP.

Incluye un **modo simulado (Mock)** para desarrollar y probar sin
disponer de una cámara física: la interfaz PTZ es independiente del
protocolo, por lo que se puede sustituir ONVIF por otro protocolo en el
futuro sin tocar el resto del sistema.

## Requisitos

- Linux o Windows
- Para usarlo desde el ejecutable: **nada más**
- Para ejecutarlo desde el código: Python 3.12+ (verificado con 3.13) y
  [uv](https://docs.astral.sh/uv/)

## Instalación

### Ejecutable (usuario final)

Descargue el paquete de su plataforma desde la página de
[Releases](https://github.com/Jaru03/ptz-controller/releases) y ejecute el
instalador que trae dentro. No hace falta Python ni permisos de
administrador: todo se instala en el perfil del usuario.

```bash
# Linux
tar -xzf ptz-controller-linux-x86_64.tar.gz
cd ptz-controller-linux-x86_64
./install.sh              # instala en ~/.local/bin y en el menú de aplicaciones
./install.sh --uninstall  # desinstala (conserva la configuración)
```

```powershell
# Windows: descomprima el .zip y, dentro de la carpeta,
powershell -ExecutionPolicy Bypass -File install.ps1
powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
```

La primera vez que arranca crea su configuración comentada en
`~/.config/ptz-controller/config.yaml` (Linux) o
`%APPDATA%\ptz-controller\config.yaml` (Windows), junto con los logs.
Ahí se indican la IP, el usuario y la contraseña de la cámara.

### Desde el código (desarrollo)

```bash
cd ptz-controller
uv sync --group dev --group gtk   # --group gtk solo hace falta en Linux
cd frontend && pnpm install && pnpm run build && cd ..
uv run python main.py
```

`--group gtk` instala los bindings de Python para GTK que necesita
pywebview en Linux (`pygobject`/`pycairo`); requiere tener instaladas las
cabeceras de desarrollo del sistema (`gobject-introspection-devel`/
`libgirepository1.0-dev`, `cairo-gobject-devel`/`libcairo2-dev`,
`python3-devel`) y, para que la ventana llegue a abrir, WebKitGTK en
tiempo de ejecución (`webkit2gtk4.1`/`gir1.2-webkit2-4.1`,
`python3-gobject`/`python3-gi`). En Windows no hace falta nada de esto:
pywebview usa Edge WebView2, que ya viene instalado. El frontend
(`frontend/dist/`) hay que reconstruirlo cada vez que cambie algo en
`frontend/src/`; en el resto del código, `uv run python main.py` recoge
los cambios directamente. En este modo la configuración y los logs
siguen viviendo en la raíz del proyecto, como siempre.

### Construir el ejecutable

```bash
uv sync --group build --group gtk
cd frontend && pnpm install && pnpm run build && cd ..
uv run --group build python packaging/build.py --clean --skip-icons
```

Deja `dist/ptz-controller` (o `dist/ptz-controller.exe`), un binario
autocontenido de unos 150 MB que incluye Python, el frontend
compilado, OpenCV y los WSDL de ONVIF. PyInstaller **no** hace
compilación cruzada: cada binario debe construirse en su plataforma. El
workflow `Build` de GitHub Actions genera ambos y los publica al
etiquetar una versión `vX.Y.Z`.

## Uso

Instalado como ejecutable, se lanza desde el menú de aplicaciones (con la
acción *Modo simulado* disponible en Linux) o desde la terminal:

```bash
ptz-controller --real     # cámara real ONVIF
ptz-controller --mock     # modo simulado
```

Desde el código:

```bash
# Modo simulado (recomendado para probar sin cámara)
uv run python main.py

# Cámara real ONVIF (usa config.yaml)
uv run python main.py --real

# Opciones útiles
uv run python main.py --config ruta/otra.yaml
uv run python main.py --no-joystick
uv run python main.py --log-level DEBUG
```

La primera vez se genera automáticamente el `config.yaml`: desde el
ejecutable a partir de la plantilla comentada `config.yaml.example`, y
desde el código a partir de los valores por defecto.

## Controles

### Teclado

| Tecla | Acción |
| --- | --- |
| W / S / A / D | Arriba / Abajo / Izquierda / Derecha (diagonales soportadas) |
| E / Q | Zoom + / Zoom - |
| 1 … 9, 0 (también en el pad numérico) | Ir a la escena 1ª … 10ª |
| ESPACIO | Stop |
| ESC | Salir |

Solo se envían comandos a la cámara cuando la dirección cambia. Las teclas
de escena se asignan **por posición** a los presets que devuelve la cámara
(`config.yaml` → `keyboard.preset_keys`), así que funcionan con cualquier
token ONVIF, incluidos los que no son números, y no hay que tocar nada al
añadir escenas. Para fijar una tecla a un token concreto está
`keyboard.preset_hotkeys` (p. ej. `f1: PresetEntrada`), que tiene
prioridad. La lista de presets de la interfaz muestra el token y la tecla
de cada escena. La velocidad se ajusta con el deslizador de la interfaz o
con el mando.

El zoom se controla con `movement.zoom_mode`: `step` (por defecto vía
`auto`) avanza a saltos de `movement.zoom_step` con `RelativeMove`, de
modo que se puede parar en posiciones intermedias aunque el firmware de
la cámara ignore el `Stop` del eje de zoom; `continuous` usa
`ContinuousMove` + `Stop` como el pan/tilt.

### Mando (joystick)

| Control | Acción |
| --- | --- |
| Stick izquierdo | Pan / Tilt proporcional |
| R2 / L2 | Zoom + / Zoom - |
| R1 / L1 | Velocidad + / Velocidad - |
| Botones (por defecto 0-3) | Ir a la escena 1ª - 4ª |
| PS / Home | Home |

El mando se detecta automáticamente (hotplug incluido). El movimiento es
proporcional al desplazamiento del stick, con zona muerta re-escalada
(20% de stick → 20% de velocidad). Los mapeos pueden adaptarse por mando
en `config.yaml` → `joystick.device_overrides`.

## Backend de teclado

`config.yaml` → `keyboard.backend`:

- `auto` (por defecto): intenta **pynput** (teclado global). Si no puede
  arrancar (p. ej. Wayland sin X11 o sin permisos del grupo `input`),
  cae automáticamente a la captura de eventos de la **ventana**, que
  funciona en cualquier entorno con foco en la aplicación.
- `pynput`: solo teclado global.
- `window`: solo eventos de la ventana (se llamaba `qt` antes de la
  migración a pywebview; ese valor se sigue aceptando).

## Arquitectura

```
ptz-controller/
├── main.py                    # Bootstrap: wiring de todas las capas
├── config.yaml                # Configuración (YAML)
├── config/                    # Carga/guardado de la configuración
├── models/                    # Comandos y estado PTZ (dominio)
├── camera/
│   ├── ptz_controller.py      # Interfaz PTZController + ONVIF
│   ├── client.py              # Cliente ONVIF (onvif-zeep)
│   ├── mock_ptz.py            # Cámara simulada (Mock)
│   └── discovery.py           # Descubrimiento WS-Discovery (UDP)
├── controllers/               # Entrada: teclado y joystick
├── core/                      # EventBus (mediador), Ref, worker de comandos y captura de vídeo
├── gui_web/                   # Puente Python↔JS (Api, EventBridge, servidor MJPEG)
├── frontend/                  # Interfaz React + TypeScript + Tailwind + shadcn/ui
│   └── src/
│       ├── pages/             # ConnectionScreen, MainScreen
│       ├── components/        # Paneles: cámara, vídeo, presets, ajustes, controles...
│       └── lib/                # bridge.ts, api.ts, keymap.ts, tipos compartidos
├── utils/                     # Logging y resolución de rutas
├── packaging/                 # Ejecutable (PyInstaller), iconos e instaladores
└── tests/                     # pytest
```

Principios aplicados: SOLID, DRY, KISS, YAGNI, PEP 8, type hints y
docstrings. La comunicación entre capas ocurre exclusivamente a través
del `EventBus` (pub/sub): los controladores de entrada publican comandos,
`main.py` los enruta al controlador PTZ activo, y `gui_web/bridge.py`
reenvía los eventos de estado al frontend (React) vía pywebview.

## Documentación por módulo

- **`models/commands.py`** — Comandos inmutables (`MoveCommand`,
  `StopCommand`, presets, etc.) y `PTZStatus`, el "lenguaje" del sistema.
- **`core/event_bus.py`** — `EventBus` seguro para hilos; temas `command.*`,
  `ptz.status`, `ptz.presets`, `ptz.stream`, `input.keyboard`,
  `input.joystick`, etc.
- **`core/command_worker.py`** — Ejecuta el trabajo de cámara (peticiones
  SOAP) en un hilo propio, fusionando los comandos repetidos, para no
  bloquear el hilo de la GUI.
- **`camera/ptz_controller.py`** — `PTZController` (ABC) e implementación
  ONVIF sobre `OnvifClient`.
- **`camera/client.py`** — Servicios Media/PTZ/Device: ContinuousMove,
  Stop, AbsoluteMove, RelativeMove, Goto/Set/RemovePreset, GetStatus,
  GetProfiles, GetDeviceInformation, GetStreamUri.
- **`camera/mock_ptz.py`** — PTZ virtual que integra el movimiento y
  notifica instantáneas; no requiere hardware.
- **`camera/discovery.py`** — WS-Discovery por UDP multicast (sin
  dependencias adicionales).
- **`controllers/base.py`** — `MovementState` (zona muerta re-escalada,
  emisión solo ante cambios de dirección y reenvío periódico) y
  `PresetRegistry` (posición → token ONVIF), usados por teclado y mando.
- **`controllers/keyboard_controller.py`** — Backends pynput/ventana con
  la misma lógica.
- **`controllers/pygame_events.py`** — Bucle de eventos SDL compartido
  (driver dummy) con hotplug de mandos.
- **`controllers/joystick_controller.py`** — Movimiento proporcional por
  ejes, zoom por gatillos, velocidad y presets por botones.
- **`core/video_stream.py`** — Vista previa RTSP con OpenCV en un hilo:
  transporte configurable, timeouts de socket, reconexión con backoff y
  limitación de fps solo en la entrega de frames.
- **`gui_web/bridge.py`** — `EventBridge`: reenvía los topics del bus al
  frontend vía `window.evaluate_js(...)`.
- **`gui_web/api.py`** — `Api`, expuesta como `window.pywebview.api`: cada
  método corresponde a una acción de la interfaz (conectar, mover,
  presets, ajustes, teclado...), enviada al `EventBus` con `bus.send`.
- **`gui_web/video_server.py`** — Servidor HTTP local que sirve el vídeo
  como MJPEG (`multipart/x-mixed-replace`) para el `<img>` del frontend.
- **`frontend/src/pages/MainScreen.tsx`** — Pestañas (vista previa,
  simulación, controles, actualizaciones) y panel lateral (conexión,
  estado, velocidad, presets, ajustes).
- **`frontend/src/components/camera/CameraStatusPanel.tsx`** —
  Representación visual de la cámara en `<canvas>` (punto, ejes, flechas,
  zoom, velocidad).
- **`utils/logger.py`** — Logging a consola y archivo rotativo
  (`logs/ptz-controller.log`).
- **`utils/paths.py`** — Decide dónde viven recursos, configuración y logs
  según se ejecute desde el código o desde un ejecutable empaquetado.
- **`packaging/`** — `build.py` (construye el binario), el `.spec` de
  PyInstaller, `make_icons.py` (SVG → PNG/ICO) e `install.sh` /
  `install.ps1` para instalar en el perfil del usuario.

## Tests

```bash
uv run pytest
```

Cubren el bus de eventos, los comandos, la configuración YAML, el
controlador simulado, la capa de entrada y el puente Python↔JS
(`gui_web/`, sin necesitar abrir ninguna ventana real). El frontend
(`frontend/`) se verifica con `pnpm run build` (comprobación de tipos)
más revisión manual en navegador; no tiene tests automatizados propios
todavía.

## Futuras ampliaciones

La arquitectura está pensada para añadir sin reescribir: detección
automática de cámaras (ya incluida), control por navegador (FastAPI),
móvil, Stream Deck, MIDI, OSC, múltiples cámaras, macros, seguimiento
por IA o reconocimiento de gestos: basta con añadir nuevos
`InputController` o `PTZController` y registrarlos en el `EventBus`.

## Limitaciones

- La vista previa RTSP solo funciona con una cámara real; en modo Mock se
  muestra la representación virtual.
- Las cámaras varían en su soporte ONVIF; los errores SOAP se registran y
  se muestran en la interfaz.
- El teclado global (pynput) puede requerir X11 o pertenecer al grupo
  `input` en Linux; el backend `window` no tiene ese requisito.
- No expongas credenciales de cámara en repositorios públicos: `config.yaml`
  está pensado para el usuario, no para versionarse con secretos.
