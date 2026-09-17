"""Fase 2 - filtro determinista por palabras clave (sin IA).

Es la fase que controla el coste: el modelo solo vera lo que pase de aqui.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from negocio.extraccion import normalizar

LONGITUD_CONTEXTO = 300


@dataclass
class Coincidencia:
    terminos: list[str]
    contextos: dict[str, str]

    @property
    def hay(self) -> bool:
        return bool(self.terminos)


def buscar(texto: str, terminos: list[str]) -> Coincidencia:
    """Busca los terminos en el texto normalizado y guarda 300 caracteres de contexto."""
    plano = normalizar(texto)
    encontrados: list[str] = []
    contextos: dict[str, str] = {}

    for termino in terminos:
        aguja = normalizar(termino)
        if not aguja:
            continue
        patron = re.compile(rf"(?<![a-z0-9]){re.escape(aguja)}(?![a-z0-9])")
        encontrado = patron.search(plano)
        if encontrado is None:
            continue
        encontrados.append(termino)
        inicio = max(0, encontrado.start() - LONGITUD_CONTEXTO // 2)
        fin = min(len(plano), encontrado.end() + LONGITUD_CONTEXTO // 2)
        contextos[termino] = plano[inicio:fin].strip()

    return Coincidencia(terminos=encontrados, contextos=contextos)
