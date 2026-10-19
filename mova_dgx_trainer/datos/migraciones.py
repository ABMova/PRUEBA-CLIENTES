"""Aplicación idempotente de las migraciones de `esquema.py`."""
from __future__ import annotations

import sqlite3

from datos.esquema import MIGRACIONES


def version(conexion: sqlite3.Connection) -> int:
    return int(conexion.execute("PRAGMA user_version").fetchone()[0])


def _columna_existe(conexion: sqlite3.Connection, tabla: str, columna: str) -> bool:
    return any(f[1] == columna for f in conexion.execute(f"PRAGMA table_info({tabla})"))


def aplicar(conexion: sqlite3.Connection, hasta: int | None = None) -> tuple[int, int]:
    """Lleva la base a la última versión (o a `hasta`). Devuelve (desde, hasta)."""
    desde = version(conexion)
    actual = desde
    for numero, sentencias in MIGRACIONES:
        if numero <= actual or (hasta is not None and numero > hasta):
            continue
        with conexion:
            for s in sentencias:
                if isinstance(s, tuple) and s[0] == "ADD_COLUMN":
                    _, tabla, columna, tipo = s
                    if not _columna_existe(conexion, tabla, columna):
                        conexion.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
                else:
                    conexion.execute(s)
            conexion.execute(f"PRAGMA user_version = {int(numero)}")
        actual = numero
    return desde, actual
