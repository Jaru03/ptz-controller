# AGENTS.md — Contexto para agentes

Este documento reúne el estado del proyecto y, sobre todo, el contexto de
trabajo reciente para que otro agente (o una nueva sesión) pueda continuar
sin perder el hilo.

## Proyecto

`ptz-controller` es un controlador de cámaras PTZ compatibles con ONVIF:
teclado (WASD) y mando SDL, movimiento proporcional, presets, y una GUI
PySide6 con vista previa RTSP. Incluye un modo simulado (Mock) para
desarrollar sin hardware.

- Lenguaje del proyecto y de los mensajes de usuario: **español**.
- Python 3.12+ (verificado con 3.13), gestión de dependencias con **uv**.
- Código: PEP 8, type hints, docstrings en español, SOLID/DRY/KISS.
- Comunicación entre capas solo vía `EventBus` (pub/sub).

## Comandos

```bash
uv sync --group dev                 # instalar dependencias (incl. pytest)
uv run python main.py               # modo simulado (Mock)
uv run python main.py --real        # cámara real ONVIF (config.yaml)
uv run python main.py --log-level DEBUG
uv run pytest                       # 77 tests (offscreen Qt)
```

## Arquitectura (resumen)

```
main.py                 # bootstrap / wiring de capas y rutas del bus
config/                 # dataclasses + carga/guardado YAML (deep merge)
models/commands.py      # comandos inmutables, PTZStatus, PresetInfo
camera/ptz_controller.py# PTZController (ABC) + OnvifPTZController
camera/client.py        # OnvifClient (onvif-zeep): Media/PTZ/Device
camera/mock_ptz.py      # PTZ virtual con integración determinista
camera/discovery.py     # WS-Discovery por UDP
controllers/            # entrada: MovementState, teclado (pynput/Qt), joystick
core/event_bus.py       # EventBus thread-safe + Ref
gui/                    # PySide6: main_window, camera_widget, video_widget, settings_dialog
utils/logger.py         # logging consola + archivo rotativo
tests/                  # pytest (79 tests)
```

Temas del bus: `command.move`, `command.stop`, `command.gotoPreset`,
`command.setPreset`, `command.renamePreset`, `command.removePreset`,
`command.connect/disconnect`, `command.setSpeed`, `command.quit`,
`ptz.status`, `ptz.presets`, `input.keyboard`, `input.joystick`,
`gui.error`, `gui.discovery`.

## Estado del repositorio (importante)

Hay **cambios sin commitear** correspondientes a la sesión de trabajo
actual (fixes de vídeo RTSP, presets por token, zoom y reenvío periódico
de movimiento). Ver `git status`:
modificados `camera/client.py`, `camera/mock_ptz.py`, `config/settings.py`,
`config.yaml.example`, `controllers/base.py`, `gui/main_window.py`,
`gui/video_widget.py`, `main.py`, `models/commands.py`,
`tests/test_client.py`, `tests/test_controllers.py`, `utils/logger.py` y
nuevos `tests/test_video_widget.py` y `AGENTS.md`. **No commitear sin que
el usuario lo pida.**

---

## Contexto técnico de la sesión

### Entorno físico del usuario (importante para debugging)

- Portátil del usuario: **por WiFi** (punto débil de la red).
- Cámara PTZ: por **Ethernet** a otro PC, que también va por Ethernet.
- Cámara: ONVIF en `192.168.100.205:8080` (perfil con presets ya
  guardados desde el navegador web de la cámara).
- El stream en el PC cableado se ve limpio; en el portátil (WiFi) se veía
  distorsionado y con retardo. Conclusión: pérdida de paquetes en el salto
  WiFi, no en la cámara ni en la app.

### Errores H.264 en la vista previa RTSP (`reference picture missing`, `mmco: unref short failure`, `illegal short term buffer state detected`)

Causa: pérdida de paquetes RTP (transporte UDP) + unión al stream a mitad
de GOP (faltan los frames de referencia). Con TCP la pérdida desaparece;
los errores residuales al conectar son no fatales y se recuperan en el
siguiente keyframe (IDR).

Fixes aplicados en `gui/video_widget.py`:

1. **Transporte TCP** vía variable de entorno de OpenCV FFmpeg backend:
   ```python
   os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
   ```
   - Formato de la variable: pares `clave;valor` separados por `|`
     (lo parsea `av_dict_parse_string(..., ";", "|", 0)`). No usar `=` ni `,`.
   - `stimeout` está en **microsegundos** (5 s). Evita que `read()` se
     bloquee indefinidamente y permite la reconexión.
   - Debe setearse **antes** de crear el `cv2.VideoCapture` (lo hace
     `VideoStreamThread._open_capture()`).
   - Verificado en OpenCV 5.0.0 (wheel `opencv-python`, backend ffmpeg).
   - Configurable en `config.yaml` → `gui.rtsp_transport` (default `tcp`).

2. **Silenciar el ruido del decodificador H.264**:
   ```python
   os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "0"   # AV_LOG_PANIC
   ```
   - Si el logger de la app está en DEBUG, se usa `"32"` (INFO) para
     depurar. Decidido por `build_ffmpeg_loglevel()` en función de
     `utils.logger.get_app_log_level()`.
   - Estos mensajes se imprimen directamente por libav (formato
     `[h264 @ 0x...]`) incluso con el nivel por defecto de OpenCV, porque
     son AV_LOG_ERROR.

3. **Reconexión automática con backoff exponencial**:
   - Delay base 1 s, máx 8 s (`_RECONNECT_BASE_DELAY_S`,
     `_RECONNECT_MAX_DELAY_S`). `_sleep_reconnect(retries)` comprueba
     `_running` en fragmentos de 50 ms para no bloquear `stop()`.
   - Antes: el hilo moría con el primer fallo; ahora reintenta en segundo
     plano (solo emite `stream_error` en el primer fallo de apertura).

Nota de diagnóstico: si quieres reproducir los errores sin cámara, genera
un `.h264` truncado a mitad de GOP y ábrelo con OpenCV:
```bash
ffmpeg -f lavfi -i testsrc=size=320x240:rate=25 -t 3 -c:v libopenh264 -g 25 -b:v 400k full.h264
dd if=full.h264 of=cut.h264 bs=1 skip=30000   # empieza sin IDR
```

### Presets de la cámara (escenas ya guardadas)

Problema original: `get_presets()` convertía el token ONVIF con
`int(str(token))` y **descartaba en silencio** los presets con tokens no
numéricos (p. ej. `"PresetA"`, UUIDs). El usuario veía sus escenas en el
navegador de la cámara pero no aparecían en la app.

Fixes aplicados:

- `models/commands.py` → `PresetInfo` ahora tiene `preset_id: int`
  (solo para la GUI) **y** `token: str` (token ONVIF real).
- `camera/client.py`:
  - `OnvifClient._preset_tokens: dict[int, str]` guarda el mapeo
    id→token, poblado en `get_presets()` y limpiado en `disconnect()`.
  - `_preset_id_for_token(token)`: si el token es numérico lo usa tal
    cual; si no, deriva un entero estable con `zlib.crc32(token) & 0x7FFFFFFF`
    (determinista, los tokens no cambian).
  - `goto_preset` / `remove_preset` / `rename_preset` usan
    `_preset_token(preset_id)` (token real, con fallback a `str(id)`).
- `camera/mock_ptz.py`: `PresetInfo` incluye `token=str(preset_id)`.
- `gui/main_window.py` `_on_presets`: muestra `Nombre  [token]` y guarda
  el token en `UserRole + 2`.

La interfaz numérica (comandos, hotkeys `preset_hotkeys: {"1": 1, ...}`,
`_prompt_preset`) se mantiene: el número se resuelve al token real en la
capa de cliente.

### Zoom (E/Q) y ContinuousMove

- Se cambió `continuous_move()` para **enviar solo los ejes activos**
  (`PanTilt` y/o `Zoom` por separado), en vez de mandar siempre
  `PanTilt {0,0}` + `Zoom`. Razón: algunas cámaras ignoran el zoom si
  reciben `PanTilt` vacío a la vez; el estándar ONVIF permite omitir
  componentes inactivos.
- **Pendiente de confirmar**: el usuario aún no ha probado si el zoom
  funciona con este cambio. Si sigue sin funcionar, la cámara probablemente
  no soporta zoom continuo por ONVIF (probar AbsoluteMove de zoom o la web
  de la cámara).

### Desaceleración / parada del movimiento (pan) — mitigación aplicada

El usuario nota que, manteniendo una tecla de dirección, la cámara **frena
o se queda detenida aunque quede mucho rango** (y a veces no reanuda con
el teclado). La causa más probable es **firmware de la cámara** que se
detiene si no recibe paquetes `ContinuousMove` periódicos, o que
interpreta la velocidad como fracción del recorrido restante.

**Mitigación implementada (opción "Turbo" elegida por el usuario)**: en
`controllers/base.py`, `MovementState` ahora **reenvía periódicamente** el
último `MoveCommand` mientras la dirección esté activa (hilo auxiliar
`movement-repeat`, default cada **150 ms**, configurable en `config.yaml`
→ `movement.repeat_interval_ms`). Al volver a neutro publica `StopCommand`
y detiene el hilo. Detalles:

- `MovementState.__init__(..., repeat_interval=0.15)`: intervalo en
  segundos (mínimo 30 ms); `main.py` lo pasa como
  `settings.movement.repeat_interval_ms / 1000.0`.
- La emisión inicial sigue siendo solo al cambiar de dirección (DRY); el
  reenvío periódico repite el mismo comando sin cambios.
- El hilo publica **bajo el `RLock`** para que la secuencia move→stop sea
  atómica y no pueda emitirse un `MoveCommand` obsoleto tras el `Stop`.
- `set_speed`/`update` protegen el estado con el mismo lock (el estado se
  comparte entre teclado y joystick).
- Tests nuevos en `tests/test_controllers.py`:
  `test_movement_state_repeats_while_held` y
  `test_movement_state_stops_repeating_after_neutral`.

**Pendiente de confirmar**: el usuario aún no ha probado en hardware si el
reenvío periódico elimina la parada/desaceleración. Si no lo arregla,
quedan como alternativas:
1. **RelativeMove por pasos**: enviar traslaciones fijas a velocidad 1.0,
   que en muchas cámaras no decelera con la posición.
2. Revisar en la web de la cámara ajustes tipo "pan speed" / modo continuo.

El zoom (E/Q) también está pendiente de confirmar tras el cambio de enviar
solo ejes activos (ver sección anterior).

## Convenciones a respetar

- Docstrings y logs en español; código con type hints y nombres en inglés.
- `# noqa` solo donde hace falta; mantener los `# noqa: BLE001` existentes
  para errores variados de red/SOAP.
- No añadir comentarios innecesarios al código.
- Ejecutar siempre `uv run pytest` tras cambios (79 tests) y, si hay GUI,
  verificar con la plataforma `offscreen` (ya configurada en los tests).
- `config.yaml` real del usuario NO se versiona (está en `.gitignore`).
  Editar `config.yaml.example` para cambios de configuración.
