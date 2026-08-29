"""Serialización de payloads del bus hacia JSON para el frontend.

Los payloads que circulan por el ``EventBus`` son dataclasses inmutables
(``PTZStatus``, ``PresetInfo``, comandos...), tuplas, enums o tipos ya
JSON-nativos (``str``, listas de dicts). :func:`to_json_safe` los reduce a
algo que ``json.dumps``/``window.evaluate_js`` pueda tragar sin más, para
usarse tanto en :mod:`gui_web.bridge` (Python -> JS) como en
:mod:`gui_web.api` (valores de retorno JS -> Python, que pywebview también
serializa como JSON).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any


def to_json_safe(value: Any) -> Any:
    """Convierte un valor del dominio de la app en algo JSON-serializable.

    Entiende dataclasses (recursivamente, incluidos sus campos anidados),
    ``Enum`` (se queda con ``.value``), y tuplas/listas/dicts (recorridos
    elemento a elemento). Cualquier otro tipo se devuelve tal cual, como
    hace ``json.dumps`` con los tipos nativos.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_json_safe(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}
    return value
