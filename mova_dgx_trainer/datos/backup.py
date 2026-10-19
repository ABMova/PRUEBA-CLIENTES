"""Copias de seguridad de la base de datos con la API de copia de SQLite."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

PREFIJO = "trainer_"
MAX_COPIAS = 10


def _copiar(origen: Path, destino: Path) -> None:
    fuente = sqlite3.connect(str(origen))
    try:
        dest = sqlite3.connect(str(destino))
        try:
            fuente.backup(dest)
        finally:
            dest.close()
    finally:
        fuente.close()


def crear_copia(ruta_bd: Path, carpeta: Path, etiqueta: str = "auto",
                maximo: int | None = MAX_COPIAS) -> Path | None:
    """Copia la base y rota para conservar las `maximo` últimas."""
    if not Path(ruta_bd).exists():
        return None
    carpeta.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = carpeta / f"{PREFIJO}{sello}_{etiqueta}.db"
    _copiar(Path(ruta_bd), destino)
    if maximo is not None:
        rotar(carpeta, maximo)
    return destino


def listar(carpeta: Path) -> list[Path]:
    if not carpeta.exists():
        return []
    return sorted(carpeta.glob(f"{PREFIJO}*.db"), key=lambda p: p.name, reverse=True)


def rotar(carpeta: Path, maximo: int = MAX_COPIAS) -> list[Path]:
    sobrantes = listar(carpeta)[maximo:]
    for p in sobrantes:
        p.unlink(missing_ok=True)
    return sobrantes


def restaurar(copia: Path, ruta_bd: Path, carpeta: Path) -> Path | None:
    """Restaura `copia` sobre la base actual, guardando antes una copia de seguridad."""
    if not Path(copia).exists():
        raise FileNotFoundError(copia)
    # Se rota después de restaurar: la copia elegida podría ser la más antigua.
    seguridad = crear_copia(ruta_bd, carpeta, "antes_de_restaurar", maximo=None)
    _copiar(Path(copia), Path(ruta_bd))
    rotar(carpeta)
    return seguridad
