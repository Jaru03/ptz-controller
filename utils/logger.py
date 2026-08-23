"""Configuración del sistema de logging.

Proporciona un único punto de entrada para configurar el logging de la
aplicación: consola + archivo rotativo (utf-8). Los demás módulos obtienen
sus loggers con ``get_logger(__name__)``.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_LOGGER_NAME = "ptz_controller"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger con el nombre del módulo solicitado."""
    return logging.getLogger(f"{APP_LOGGER_NAME}.{name.lstrip('.')}")


def get_app_log_level() -> int:
    """Nivel efectivo (int de ``logging``) del logger de la aplicación."""
    return logging.getLogger(APP_LOGGER_NAME).getEffectiveLevel()


def setup_logging(
    level: str = "INFO",
    log_dir: str | Path = "logs",
    log_filename: str = "ptz-controller.log",
) -> logging.Logger:
    """Configura el logger raíz de la aplicación (consola + archivo).

    Es seguro llamarla varias veces: elimina handlers previos para evitar
    duplicados.

    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directorio donde se guarda el archivo de logs.
        log_filename: Nombre del archivo de logs.

    Returns:
        El logger de la aplicación.
    """
    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(level.upper())
    # Evita que los registros se propaguen al root y se impriman dos veces.
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    try:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / log_filename,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - permisos/entorno de solo lectura
        logger.warning("No se pudo crear el archivo de logs: %s", exc)

    return logger
