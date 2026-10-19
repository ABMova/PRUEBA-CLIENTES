"""Configuración del log de la aplicación (fichero en almacen/logs)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configurar(carpeta_logs: Path, nivel: int = logging.INFO) -> Path:
    carpeta_logs.mkdir(parents=True, exist_ok=True)
    ruta = carpeta_logs / "aplicacion.log"
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    if not any(isinstance(h, RotatingFileHandler) for h in raiz.handlers):
        manejador = RotatingFileHandler(ruta, maxBytes=2_000_000, backupCount=5,
                                        encoding="utf-8")
        manejador.setFormatter(logging.Formatter(FORMATO))
        raiz.addHandler(manejador)
    return ruta
