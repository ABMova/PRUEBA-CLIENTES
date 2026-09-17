"""Fase 5 - deduplicacion e historico.

Dos niveles, como se acordo (decision abierta a confirmar):
  1. hash exacto  = sha256(codigo_boletin + titulo normalizado)
  2. comparacion difusa del titulo contra los ultimos N dias (rapidfuzz)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from rapidfuzz import fuzz

from negocio.extraccion import normalizar_titulo


@dataclass
class Veredicto:
    duplicada: bool
    motivo: str = ""
    original_id: int | None = None
    similitud: int = 0


def calcular_hash(codigo_boletin: str, titulo: str) -> str:
    semilla = f"{codigo_boletin.upper()}|{normalizar_titulo(titulo)}"
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()


def comprobar(codigo_boletin: str, titulo: str, hash_contenido: str, ya_visto: bool,
              recientes: list[dict], umbral: int) -> Veredicto:
    """recientes: [{id, titulo_normalizado, codigo_boletin}] de los ultimos dias."""
    if ya_visto:
        return Veredicto(True, "Ya estaba en el historico o entre los descartes")

    titulo_plano = normalizar_titulo(titulo)
    mejor_id: int | None = None
    mejor_similitud = 0

    for anterior in recientes:
        candidato = anterior.get("titulo_normalizado") or ""
        if not candidato:
            continue
        similitud = int(fuzz.token_sort_ratio(titulo_plano, candidato))
        if similitud > mejor_similitud:
            mejor_similitud = similitud
            mejor_id = anterior.get("id")

    if mejor_similitud >= umbral:
        return Veredicto(True, f"Titulo casi identico a una publicacion anterior "
                               f"(similitud {mejor_similitud}%)", mejor_id, mejor_similitud)
    return Veredicto(False, similitud=mejor_similitud)
