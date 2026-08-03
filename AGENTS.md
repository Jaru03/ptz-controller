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
uv run pytest                       # 122 tests (offscreen Qt)

uv sync --group build                              # PyInstaller
uv run --group build python packaging/build.py --clean   # dist/ptz-controller
./packaging/install.sh                             # instala en ~/.local
uv run --group build python packaging/build_rpm.py # RPM Fedora (dist/rpm/RPMS)
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
controllers/            # entrada: MovementState, PresetRegistry, teclado (pynput/Qt), joystick
core/event_bus.py       # EventBus thread-safe + Ref
core/command_worker.py  # hilo que ejecuta el trabajo ONVIF fuera de la GUI
gui/                    # PySide6: main_window, camera_widget, video_widget, settings_dialog
utils/logger.py         # logging consola + archivo rotativo
utils/paths.py          # rutas: recursos del bundle vs directorio del usuario
packaging/              # PyInstaller (.spec, build.py), iconos e instaladores
tests/                  # pytest (122 tests)
```

Temas del bus: `command.move`, `command.stop`, `command.gotoPreset`,
`command.setPreset`, `command.renamePreset`, `command.removePreset`,
`command.connect/disconnect`, `command.setSpeed`, `command.quit`,
`ptz.status`, `ptz.presets`, `ptz.stream`, `input.keyboard`,
`input.joystick`, `gui.error`, `gui.discovery`.

**Regla de oro**: ninguna llamada ONVIF debe ejecutarse en el hilo de la
GUI. El `EventBus` invoca a los handlers en el hilo del publicador, así
que `main.py` enruta todos los comandos de cámara al `CommandWorker`.

## Estado del repositorio

`master` en `bc25718` (merge del PR #1), sin cambios pendientes. Todo el
trabajo descrito más abajo está commiteado y publicado.
**No commitear sin que el usuario lo pida.**

### Release v0.1.0 (2026-08-03)

Primera versión publicada:
<https://github.com/Jaru03/ptz-controller/releases/tag/v0.1.0>

- `ptz-controller-linux-x86_64.tar.gz` (169 MB) — binario + `install.sh`
  + icono.
- `ptz-controller-windows-x86_64.zip` (113 MB) — `.exe` + `install.ps1`.
- Release pública, ni borrador ni prerelease.

Commits de la versión:

- `57359fd` fix: estabilidad de vídeo, presets por token, pad numérico y
  zoom por pasos.
- `7ab322b` feat: instalador y ejecutable autocontenido.

Verificado en CI (Linux y Windows en verde, tanto `CI` como `Build`) y a
mano: descarga del `.tar.gz` publicado, extracción fuera del repo,
`install.sh`, arranque desde `~/.local/bin` y creación de la
configuración en `~/.config/ptz-controller/`. La prueba de humo del
runner de Windows confirma que el `.exe` arranca y crea su configuración
en `%APPDATA%`.

La siguiente versión solo necesita: mergear a `master`, comprobar que el
workflow `Build` pasa (lanzándolo con `workflow_dispatch`) y etiquetar
`vX.Y.Z`. Mantener `version` de `pyproject.toml` alineada con la
etiqueta.

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
   os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = build_ffmpeg_options("tcp")
   ```
   - Formato de la variable: pares `clave;valor` separados por `|`
     (lo parsea `av_dict_parse_string(..., ";", "|", 0)`). No usar `=` ni `,`.
   - **`stimeout` ya no existe**: FFmpeg lo renombró a `timeout` en la
     versión 5 y OpenCV 5.0.0 trae avformat 62 (FFmpeg 8), así que la
     opción se ignoraba en silencio y `read()` podía bloquearse para
     siempre. Se envían **las dos** claves (la que no exista se ignora).
     Comprobar con `ffmpeg -h demuxer=rtsp`.
   - Timeout en **microsegundos** (5 s). Además: `max_delay`,
     `buffer_size`, `fflags;nobuffer`, `flags;low_delay` y, en TCP,
     `reorder_queue_size;0`.
   - Debe setearse **antes** de crear el `cv2.VideoCapture` (lo hace
     `VideoStreamThread._open_capture()`).
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
   - Un fallo aislado de `read()` ya no tira la conexión: hacen falta
     `_MAX_READ_FAILURES` (3) seguidos.

4. **No dormir entre lecturas** (`_consume`): `read()` ya bloquea hasta
   el siguiente frame, así que el `time.sleep(1/fps)` que había hacía que
   se consumiera **más despacio de lo que la cámara emite**; el búfer de
   recepción se llenaba y la imagen llegaba con retardo creciente, a
   tirones y con cortes. Ahora se lee sin pausa y el límite de fps se
   aplica solo al emitir hacia la GUI (los frames sobrantes se descartan).

5. **`VideoWidget.stop()` estaba roto**: llamaba a
   `QThread.wait(timeout=2000)` y PySide6 no acepta ese keyword, así que
   lanzaba `TypeError` dentro del slot. Consecuencia: al desconectar no se
   paraba el hilo de captura ni se limpiaba `_video_url`, y **cada
   reconexión dejaba otro hilo decodificando el mismo stream y pintando en
   el mismo label**. Ahora se usa `wait(500)` posicional y, si el hilo no
   termina, se le desconectan las señales y se guarda en `_stopping`
   hasta que muera.

### Llamadas ONVIF bloqueando la GUI (causa principal de los cortes)

El `EventBus` invoca a los handlers **en el hilo del publicador**, así que
cada `MoveCommand` del teclado Qt y cada `GetStatus` del `QTimer`
ejecutaban una petición SOAP en el hilo de la GUI. Mientras tanto la
ventana no procesaba eventos, así que la vista previa se congelaba y los
frames se acumulaban. Y el transporte zeep no tenía timeout
(`connect timeout=None` en los logs), de modo que una cámara que dejaba de
responder bloqueaba la interfaz durante minutos.

Fixes:

- `core/command_worker.py` (`CommandWorker`): hilo propio con cola y
  **fusión por clave**. Un `move` pendiente se sustituye por el siguiente
  (la cola no crece aunque la cámara vaya más lenta que el teclado) y el
  `stop` descarta los `move` pendientes (`cancels=("move",)`), de modo que
  la parada no llega tarde. Un trabajo que falla no mata el hilo.
- `main.py` enruta por el worker todo: move/stop/home/presets/
  connect/disconnect y el sondeo de estado (`key="status"`).
- `OnvifClient._build_transport()`: `zeep.transports.Transport(timeout,
  operation_timeout)`. El parámetro `timeout` del cliente existía pero
  **no se usaba**.
- La URL RTSP se resuelve en el worker y se publica en el topic
  `ptz.stream`; la GUI ya no llama a `stream_uri()` (SOAP) ni a
  `get_status()` directamente.

Nota de diagnóstico: si quieres reproducir los errores sin cámara, genera
un `.h264` truncado a mitad de GOP y ábrelo con OpenCV:
```bash
ffmpeg -f lavfi -i testsrc=size=320x240:rate=25 -t 3 -c:v libopenh264 -g 25 -b:v 400k full.h264
dd if=full.h264 of=cut.h264 bs=1 skip=30000   # empieza sin IDR
```

### Desaceleración / parada del movimiento (pan) — RESUELTO

`MovementState` **reenvía periódicamente** el último `MoveCommand`
mientras la dirección esté activa (hilo `movement-repeat`, cada 150 ms
por defecto, `movement.repeat_interval_ms`). Al volver a neutro publica
`StopCommand` y detiene el hilo. Confirmado por el usuario: funciona.

- El hilo publica **bajo el `RLock`** para que la secuencia move→stop sea
  atómica y no se emita un `MoveCommand` obsoleto tras el `Stop`.
- Cada generación del hilo lleva **su propio `Event`** de parada: si se
  rearranca antes de que el anterior salga de la espera, el viejo no
  revive ni duplica los envíos.

### Presets: identificados solo por token ONVIF

Los presets se identifican **exclusivamente** por su token ONVIF, que es
opaco y puede no ser numérico. Se eliminó el `preset_id` numérico (y el
`crc32` que lo derivaba): ninguna capa debe volver a asumir que un preset
es un número.

- `PresetInfo(token, name)`; los comandos llevan `token: str`.
- `PTZController.goto_preset/set_preset/rename_preset/remove_preset`
  reciben el token. `set_preset("")` deja que la cámara asigne uno.
- `controllers/base.py` → `PresetRegistry`: se suscribe a `ptz.presets` y
  traduce **posición → token**.
- Teclado: `keyboard.preset_keys` (lista ordenada de teclas) asigna por
  posición; `keyboard.preset_hotkeys` (tecla → token) fija atajos
  concretos y tiene prioridad. Mando: `joystick.preset_buttons` igual,
  por posición.
- Por defecto hay 10 teclas (1-9, 0), no 3. Antes solo existían
  `{"1":1,"2":2,"3":3}`, y de ahí que el usuario solo alcanzara 3 escenas.

### Pad numérico

Se distingue del teclado principal con `KeypadModifier` **antes** de mirar
`event.text()`: con Bloq Num escribe los mismos caracteres que la fila de
dígitos y sin Bloq Num no escribe nada (emite Key_End, Key_Down, ...), que
era la razón de que no se reconociera.

- Nombres canónicos `kp_0`...`kp_9`, `kp_enter`, `kp_plus`, ...
- `key_aliases("kp_1") == ("kp_1", "1")`: si el pad no tiene atajo propio
  cae a su dígito, así funciona con la configuración por defecto.
- `pynput_key_name` mapea los keysyms X11 del pad (0xFFB0+) por `vk`
  **antes** de mirar `key.char`.

### Zoom (E/Q) — modos

`movement.zoom_mode`: `step` | `continuous` | `auto` (default), con
`movement.zoom_step` (0.06).

- `step`: cada repetición envía un `RelativeMove` de `zoom_step * speed`.
  El zoom avanza a saltos y **para en posiciones intermedias** aunque el
  firmware ignore el `Stop` del eje de zoom (el síntoma que reportó el
  usuario: el zoom iba de principio a fin sin puntos intermedios).
- `continuous`: `ContinuousMove` + `Stop`, como el pan/tilt.
- `auto`: intenta `step` y cae a `continuous` **de forma permanente** si
  la cámara rechaza el `RelativeMove`.
- El pan/tilt sigue siendo continuo en todos los modos. En `step` **sin**
  pan/tilt no se envía `ContinuousMove`: con todos los ejes a cero se
  traduce en un `Stop` que llegaría entre pasos y abortaría el zoom
  anterior (usar `client.stop_inactive_axes(False, False)`).

`continuous_move()` envía solo los ejes activos, y como omitir un eje
**no lo detiene** (la cámara mantiene su última velocidad), el cliente
recuerda qué ejes están en marcha y envía un `Stop` de ese eje concreto
cuando deja de enviarse. `stop(pan_tilt=True, zoom=True)` acepta ejes.

### Empaquetado (ejecutable PyInstaller)

`packaging/build.py` → `dist/ptz-controller` (~176 MB), un binario único
sin consola. Instaladores por usuario, sin root: `install.sh` (Linux:
`~/.local/bin` + `.desktop` + icono) e `install.ps1` (Windows:
`%LOCALAPPDATA%\Programs` + menú Inicio).

Tres cosas que **hay que respetar** al tocar el empaquetado:

1. **Los WSDL de onvif-zeep hay que copiarlos a mano** al bundle: viven
   en la raíz de site-packages, no dentro del paquete `onvif`, así que
   PyInstaller no los detecta. Están en `datas` del `.spec` y
   `_resolve_wsdl_dir()` mira primero `resource_dir()/wsdl`. Sin esto la
   conexión ONVIF falla solo en el ejecutable.
2. **Nada escribible junto al ejecutable**: en Linux acaba en
   `~/.local/bin` y en Windows en `Program Files`. `utils/paths.py`
   decide dónde van `config.yaml` y `logs/` según `sys.frozen`; en
   desarrollo todo sigue en la raíz del proyecto.
3. **PyInstaller no compila para otra plataforma**: el `.exe` se genera
   en el runner de Windows del workflow `Build` (`.github/workflows/
   build.yml`), que además hace una prueba de humo arrancando el binario
   y comprobando que crea su configuración.

El workflow empaqueta **un archivo por plataforma**
(`ptz-controller-linux-x86_64.tar.gz` y `…-windows-x86_64.zip`) con el
ejecutable y su instalador dentro. No subir ficheros sueltos a la
release: una release de GitHub no admite dos assets con el mismo nombre,
y `install.sh` viajaría duplicado desde los dos artefactos. Por eso los
instaladores buscan el binario **junto al propio script** y, si no, en
`dist/`.

Para publicar: `git tag vX.Y.Z && git push origin vX.Y.Z`. Solo el push
de una etiqueta `v*` dispara el job `release`; `workflow_dispatch` deja
los artefactos en la pestaña Actions (30 días, requieren sesión).

**Gotcha**: GitHub solo permite `workflow_dispatch` de workflows que ya
están en la **rama por defecto**. Lanzarlo desde una rama devuelve
`HTTP 404: workflow build.yml not found on the default branch`, así que
no se puede validar el build de Windows antes de mergear: primero se
mergea, luego se lanza a mano, y solo entonces se etiqueta (para no
dejar una etiqueta publicada con una release a medias).

Los iconos se generan del SVG con `packaging/make_icons.py` (Qt para
rasterizar y un contenedor ICO escrito a mano, sin Pillow). Al rasterizar
con Qt, el `QByteArray` debe sobrevivir al `QBuffer` o el proceso peta.

### Modo real por defecto en el build (--real)

El ejecutable empaquetado (PyInstaller) arranca en **modo cámara real**
sin pasar `--real`. `main.resolve_mock()` da ese comportamiento:
precedencia `--mock` > `--real` > (`sys.frozen` → real) > configuración.
`--mock` queda reservado para las pruebas de humo del CI. En desarrollo
(`sys.frozen` ausente) el modo por defecto sigue siendo el de
`config.yaml` (`camera.mock`). El `.desktop` (Linux) y los accesos
directos (Windows) llaman además con `--real` explícito, que queda
redundante pero explícito.

### Vista previa como primera pestaña

El orden de las pestañas de `gui/main_window.py` es: **Vista previa**,
Simulación, Controles (la pestaña inicial es la vista previa). El test
`test_controls_tab_lists_keyboard_and_joystick` fija ese orden.

### Instalador de Windows: acceso directo siempre

`packaging/install.ps1` crea **siempre** el acceso directo del escritorio
(además del del menú Inicio); se eliminó el conmutador `-DesktopShortcut`.
Los dos accesos apuntan al `.exe` con `--real`.

### RPM para Fedora

`packaging/rpm/ptz-controller.spec` + `packaging/build_rpm.py` generan un
RPM que instala el binario en `/usr/bin/ptz-controller` con el icono y la
entrada de menú (`Exec=ptz-controller --real`). El spec se llama distinto
del de PyInstaller a propósito (`packaging/rpm/`). Requisitos:

- Construir antes el binario (`packaging/build.py --clean`).
- `sudo dnf install rpm-build` (más `desktop-file-utils` si se quiere
  validar la entrada de menú).
- `build_rpm.py` lee la versión de `pyproject.toml`, crea el source
  tarball en `dist/rpm/SOURCES` y deja el RPM en
  `dist/rpm/RPMS/x86_64/`. No hay etapa de compilación: el RPM debe
  generarse en la misma distro/arquitectura que el binario.

### Pendiente de confirmar en hardware

Publicado en v0.1.0 pero **no probado aún contra la cámara real**: worker,
timeouts, `_consume` sin pausas, hilo de vídeo duplicado, zoom por pasos,
presets por posición y pad numérico. Todo está cubierto por tests y por
el arranque del binario, que no es lo mismo. Orden sugerido al probarlo:

1. Reconectar varias veces seguidas y ver si el vídeo aguanta (era el
   bug de los hilos de captura acumulados).
2. Zoom E/Q: comprobar que para en posiciones intermedias. Si va brusco o
   lento, ajustar `movement.zoom_step` / `movement.repeat_interval_ms`;
   si la cámara acepta `RelativeMove` pero no se mueve nada,
   `movement.zoom_mode: continuous`.
3. Teclas 4-9 y pad numérico contra las escenas de la cámara.

Con el ejecutable instalado, el log está en
`~/.config/ptz-controller/logs/ptz-controller.log`; con `--log-level
DEBUG` se ven los `ContinuousMove` / `RelativeMove` que salen.

## Convenciones a respetar

- Docstrings y logs en español; código con type hints y nombres en inglés.
- `# noqa` solo donde hace falta; mantener los `# noqa: BLE001` existentes
  para errores variados de red/SOAP.
- No añadir comentarios innecesarios al código.
- Ejecutar siempre `uv run pytest` tras cambios (122 tests) y, si hay GUI,
  verificar con la plataforma `offscreen` (ya configurada en los tests).
- Ninguna petición ONVIF en el hilo de la GUI: pasar por el
  `CommandWorker` (ver "Llamadas ONVIF bloqueando la GUI").
- Los presets se identifican por token ONVIF (cadena opaca), nunca por
  número.
- `config.yaml` real del usuario NO se versiona (está en `.gitignore`).
  Editar `config.yaml.example` para cambios de configuración.
