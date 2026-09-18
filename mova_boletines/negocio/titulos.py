"""Titulo resumido: que se subvenciona y a quien, en una linea.

El titulo oficial de una convocatoria es largo y empieza por la referencia
normativa ("ORDEN 12/2026, de 15 de septiembre, de la Conselleria de...").
El titulo resumido lo redacta el modelo en la fase 3. Este modulo es el
RESPALDO determinista para cuando no hay modelo (sin clave, tope de gasto
alcanzado o respuesta invalida): recorta la referencia normativa y se queda
con el objeto. Nunca anade nada que no este en el titulo original.
"""
from __future__ import annotations

import re

MAX_PALABRAS = 16

# Lo que suele preceder al objeto de la disposicion.
_CORTES = re.compile(
    r"\b(?:por (?:la|el) (?:que|cual) se|por (?:la|el) (?:que|cual)|relativ[oa] a|"
    r"sobre|referente a|para la concesion de|de convocatoria de)\b\s*",
    re.IGNORECASE)

# Verbos de tramite que no aportan al lector y se pueden quitar del comienzo.
_TRAMITE = re.compile(
    r"^(?:aprueban?|establecen?|convocan?|regulan?|modifican?|publican?|efectua|"
    r"hace publica|da publicidad a|dispone)\s*,?\s*"
    r"(?:(?:para|en) el ejercicio \d{4}\s*,?\s*)?"
    r"(?:(?:las|los|la|el)\s+)?"
    r"(?:bases reguladoras\s+(?:y\s+se\s+convocan?\s+)?)?",
    re.IGNORECASE)

_REFERENCIA = re.compile(
    r"^(?:extracto de (?:la |el )?)?(?:orden|resolucion|resolución|decreto|acuerdo|anuncio|"
    r"edicto|extracto|correccion|corrección)\b[^,]*,(?:[^,]*,)?\s*", re.IGNORECASE)


def resumir(titulo: str) -> str:
    texto = re.sub(r"\s+", " ", (titulo or "")).strip().strip(".")
    if not texto:
        return ""

    # Algunos boletines (BOCM) anteponen una etiqueta de seccion: "Convocatoria
    # subvenciones – Orden ...". Se queda lo que va despues del guion largo.
    if " – " in texto[:80]:
        texto = texto.split(" – ", 1)[1]

    partes = _CORTES.split(texto, maxsplit=1)
    if len(partes) == 2 and len(partes[1]) > 15:
        texto = partes[1]
    else:
        texto = _REFERENCIA.sub("", texto)

    texto = _TRAMITE.sub("", texto).strip(" ,;:")
    palabras = texto.split()
    if len(palabras) > MAX_PALABRAS:
        texto = " ".join(palabras[:MAX_PALABRAS]).rstrip(",;:") + "…"
    return texto[:1].upper() + texto[1:] if texto else titulo[:120]
