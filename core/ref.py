"""Referencias mutables para compartir objetos que pueden cambiarse en runtime.

``Ref`` permite que ``main.py`` sustituya el controlador PTZ activo (p.
ej. al conectar con una IP distinta desde la GUI) sin que la ventana
tenga que recibir de nuevo la referencia.
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Ref(Generic[T]):
    """Contenedor mutable de una sola referencia."""

    def __init__(self, value: T) -> None:
        self.value = value
