# ptz-controller

Controlador universal de cámaras PTZ compatibles con ONVIF.

Permite controlar una cámara PTZ desde el **teclado** (WASD) o desde un
**mando de juego** (DualShock 4/5, DualSense, Xbox o cualquier mando SDL),
con movimiento proporcional, zona muerta, presets y una interfaz gráfica
moderna (PySide6) con vista previa RTSP.

Incluye un **modo simulado (Mock)** para desarrollar y probar sin
disponer de una cámara física: la interfaz PTZ es independiente del
protocolo, por lo que se puede sustituir ONVIF por otro protocolo en el
futuro sin tocar el resto del sistema.

## Requisitos

- Python 3.12+ (proyecto desarrollado y verificado con Python 3.13)
- [uv](https://docs.astral.sh/uv/) (gestor de dependencias)
- Linux o Windows

## Instalación

```bash
cd ptz-controller
uv sync --group dev
```

## Uso

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

La primera vez se genera automáticamente `config.yaml` a partir de los
valores por defecto.

## Controles

### Teclado

| Tecla | Acción |
| --- | --- |
| W / S / A / D | Arriba / Abajo / Izquierda / Derecha (diagonales soportadas) |
| E / Q | Zoom + / Zoom - |
| 1 / 2 / 3 | Ir a escena (preset) 1 / 2 / 3 |
| ESPACIO | Stop |
| ESC | Salir |

Solo se envían comandos a la cámara cuando la dirección cambia. Las teclas
de escena son configurables: `config.yaml` → `keyboard.preset_hotkeys`
(tecla → id de preset); pulsarlas detiene el movimiento y desplaza la
cámara a esa escena. La velocidad se ajusta con el deslizador de la
interfaz o con el mando.

### Mando (joystick)

| Control | Acción |
| --- | --- |
| Stick izquierdo | Pan / Tilt proporcional |
| R2 / L2 | Zoom + / Zoom - |
| R1 / L1 | Velocidad + / Velocidad - |
| Botones (por defecto 0-3) | Ir a preset 1-4 |
| PS / Home | Home |

El mando se detecta automáticamente (hotplug incluido). El movimiento es
proporcional al desplazamiento del stick, con zona muerta re-escalada
(20% de stick → 20% de velocidad). Los mapeos pueden adaptarse por mando
en `config.yaml` → `joystick.device_overrides`.

## Backend de teclado

`config.yaml` → `keyboard.backend`:

- `auto` (por defecto): intenta **pynput** (teclado global). Si no puede
  arrancar (p. ej. Wayland sin X11 o sin permisos del grupo `input`),
  cae automáticamente a la captura de eventos de la **ventana Qt**, que
  funciona en cualquier entorno con foco en la aplicación.
- `pynput`: solo teclado global.
- `qt`: solo eventos de la ventana.

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
├── core/                      # EventBus (mediador) + Ref
├── gui/                       # PySide6 (ventana, cámara, vídeo, ajustes)
├── utils/                     # Logging (consola + archivo rotativo)
└── tests/                     # pytest
```

Principios aplicados: SOLID, DRY, KISS, YAGNI, PEP 8, type hints y
docstrings. La comunicación entre capas ocurre exclusivamente a través
del `EventBus` (pub/sub): los controladores de entrada publican comandos,
`main.py` los enruta al controlador PTZ activo y la GUI recibe
instantáneas de estado (marshalled al hilo de la interfaz).

## Documentación por módulo

- **`models/commands.py`** — Comandos inmutables (`MoveCommand`,
  `StopCommand`, presets, etc.) y `PTZStatus`, el "lenguaje" del sistema.
- **`core/event_bus.py`** — `EventBus` seguro para hilos; temas `command.*`,
  `ptz.status`, `input.keyboard`, `input.joystick`, etc.
- **`camera/ptz_controller.py`** — `PTZController` (ABC) e implementación
  ONVIF sobre `OnvifClient`.
- **`camera/client.py`** — Servicios Media/PTZ/Device: ContinuousMove,
  Stop, AbsoluteMove, RelativeMove, Goto/Set/RemovePreset, GetStatus,
  GetProfiles, GetDeviceInformation, GetStreamUri.
- **`camera/mock_ptz.py`** — PTZ virtual que integra el movimiento y
  notifica instantáneas; no requiere hardware.
- **`camera/discovery.py`** — WS-Discovery por UDP multicast (sin
  dependencias adicionales).
- **`controllers/base.py`** — `MovementState`: zona muerta re-escalada y
  emisión solo ante cambios de dirección (usado por teclado y joystick).
- **`controllers/keyboard_controller.py`** — Backends pynput/Qt con la
  misma lógica.
- **`controllers/pygame_events.py`** — Bucle de eventos SDL compartido
  (driver dummy) con hotplug de mandos.
- **`controllers/joystick_controller.py`** — Movimiento proporcional por
  ejes, zoom por gatillos, velocidad y presets por botones.
- **`gui/main_window.py`** — Ventana principal, panel de control y
  `QtEventBridge` (marshalling bus → señales Qt).
- **`gui/camera_widget.py`** — Representación visual de la cámara (punto,
  ejes, flechas, zoom, velocidad).
- **`gui/video_widget.py`** — Vista previa RTSP con OpenCV en un hilo.
- **`gui/settings_dialog.py`** — Edición de IP/puerto/usuario/velocidad/
  deadzone y guardado en YAML.
- **`utils/logger.py`** — Logging a consola y archivo rotativo
  (`logs/ptz-controller.log`).

## Tests

```bash
uv run pytest
```

Cubren el bus de eventos, los comandos, la configuración YAML, el
controlador simulado, la capa de entrada y smoke tests de la GUI
(plataforma Qt `offscreen`).

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
  `input` en Linux; el backend `qt` no tiene ese requisito.
- No expongas credenciales de cámara en repositorios públicos: `config.yaml`
  está pensado para el usuario, no para versionarse con secretos.
