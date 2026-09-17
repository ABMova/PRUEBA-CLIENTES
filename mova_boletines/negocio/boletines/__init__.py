"""Registro de adaptadores de boletin.

Anadir una comunidad nueva es: crear su modulo con la misma interfaz y
registrarlo aqui. Nada mas del sistema necesita cambiar.
"""
from __future__ import annotations

from types import ModuleType

from negocio.boletines import boja, bocm, bocyl, docm, dogc, dogv, borm

ADAPTADORES: dict[str, ModuleType] = {
    dogv.CODIGO: dogv,
    bocm.CODIGO: bocm,
    dogc.CODIGO: dogc,
    boja.CODIGO: boja,
    borm.CODIGO: borm,
    docm.CODIGO: docm,
    bocyl.CODIGO: bocyl,
}

ORDEN = ["DOGV", "BOCM", "DOGC", "BOJA", "BORM", "DOCM", "BOCYL"]


def adaptador(codigo: str) -> ModuleType:
    try:
        return ADAPTADORES[codigo.upper()]
    except KeyError as error:
        raise KeyError(f"No hay adaptador para el boletin {codigo}") from error


def fichas() -> list[dict]:
    """Datos de trazabilidad de cada adaptador, para la pantalla Boletines."""
    return [
        {
            "codigo": modulo.CODIGO,
            "nombre": modulo.NOMBRE,
            "comunidad": modulo.COMUNIDAD,
            "url": modulo.URL_COMPROBADA,
            "comprobado": modulo.FECHA_COMPROBACION,
        }
        for codigo in ORDEN
        for modulo in [ADAPTADORES[codigo]]
    ]
