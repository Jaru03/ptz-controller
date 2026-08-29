"""GUI web: shell nativo pywebview + frontend React/shadcn.

Sustituye a ``gui/`` (PySide6). Este paquete solo contiene el pegamento
entre el ``EventBus``/backend (sin cambios) y el frontend en ``frontend/``:
el puente de eventos Python→JS (:mod:`gui_web.bridge`), la API expuesta a
JS (:mod:`gui_web.api`), la serialización de payloads
(:mod:`gui_web.serialize`) y el servidor de vídeo MJPEG
(:mod:`gui_web.video_server`).
"""
