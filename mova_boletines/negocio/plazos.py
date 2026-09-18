"""Calculo determinista del fin del plazo de solicitud.

El plazo llega como texto libre ("del 1 al 30 de octubre de 2026", "10 dias
habiles desde el dia siguiente a la publicacion", "un mes a contar desde...").
Para alertar y ordenar por urgencia hace falta una fecha. Este modulo la saca
del texto sin IA, de forma trazable:

  - "fecha_literal": el texto trae la fecha escrita. Se toma la ultima.
  - "calculado": el texto da una duracion contada desde la publicacion.

Si no se puede deducir sin suponer nada, devuelve None. Nunca adivina.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from negocio.extraccion import normalizar

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}

_NUMEROS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veinticinco": 25, "treinta": 30, "cuarenta": 40,
    "cuarenta y cinco": 45, "sesenta": 60, "noventa": 90,
}

_FECHA_TEXTO = re.compile(
    r"(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")(?:\s+(?:de|del)\s+(\d{4}))?")
_FECHA_NUMERICA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_NUMERO = r"(\d{1,3}|" + "|".join(sorted(_NUMEROS, key=len, reverse=True)) + r")"
_DIAS = re.compile(_NUMERO + r"\s+dias?(\s+habiles|\s+naturales)?")
_MESES_DURACION = re.compile(_NUMERO + r"\s+(mes|meses)\b")

# Una duracion solo se calcula si se cuenta desde la publicacion. "Un mes desde
# la notificacion" o "diez dias desde la solicitud" no dan una fecha fija.
_DESDE_PUBLICACION = re.compile(
    r"(publicacion|publicado|publique|entrada en vigor|a partir del dia siguiente)")
_OTRO_ORIGEN = re.compile(r"desde (la|su) (notificacion|solicitud|resolucion|recepcion)")


def _numero(texto: str) -> int | None:
    texto = texto.strip()
    if texto.isdigit():
        return int(texto)
    return _NUMEROS.get(texto)


def _sumar_habiles(inicio: date, dias: int) -> date:
    """Dias habiles administrativos: excluye sabados y domingos (Ley 39/2015).

    No descuenta festivos: dependen de la comunidad y del municipio. Por eso el
    resultado se presenta como fecha estimada.
    """
    actual = inicio
    contados = 0
    while contados < dias:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            contados += 1
    return actual


def _sumar_meses(inicio: date, meses: int) -> date:
    mes = inicio.month - 1 + meses
    ano = inicio.year + mes // 12
    mes = mes % 12 + 1
    dia = min(inicio.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def fin_de_plazo(plazo: str, fecha_publicacion: str) -> tuple[str | None, str]:
    """Devuelve (fecha ISO o None, origen: 'fecha_literal' | 'calculado' | '')."""
    if not plazo or "[pendiente" in plazo.lower():
        return None, ""
    try:
        publicada = datetime.strptime(fecha_publicacion, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None, ""

    texto = normalizar(plazo)

    # 1) Fechas escritas: se toma la mas tardia que no sea anterior a la publicacion.
    fechas: list[date] = []
    for dia, mes, ano in _FECHA_TEXTO.findall(texto):
        anio = int(ano) if ano else publicada.year
        try:
            candidata = date(anio, _MESES[mes], int(dia))
        except ValueError:
            continue
        if not ano and candidata < publicada:
            candidata = date(anio + 1, _MESES[mes], int(dia))
        fechas.append(candidata)
    for dia, mes, ano in _FECHA_NUMERICA.findall(texto):
        try:
            fechas.append(date(int(ano), int(mes), int(dia)))
        except ValueError:
            continue
    validas = [f for f in fechas if f >= publicada]
    if validas:
        return max(validas).isoformat(), "fecha_literal"

    # 2) Duraciones contadas desde la publicacion.
    if _OTRO_ORIGEN.search(texto) or not _DESDE_PUBLICACION.search(texto):
        return None, ""

    encontrado = _DIAS.search(texto)
    if encontrado:
        cantidad = _numero(encontrado.group(1))
        if cantidad:
            if (encontrado.group(2) or "").strip() == "naturales":
                return (publicada + timedelta(days=cantidad)).isoformat(), "calculado"
            # Sin calificativo, los plazos administrativos se cuentan en habiles.
            return _sumar_habiles(publicada, cantidad).isoformat(), "calculado"

    encontrado = _MESES_DURACION.search(texto)
    if encontrado:
        cantidad = _numero(encontrado.group(1))
        if cantidad:
            return _sumar_meses(publicada, cantidad).isoformat(), "calculado"

    return None, ""


def dias_restantes(plazo_fin: str | None, hoy: date | None = None) -> int | None:
    if not plazo_fin:
        return None
    try:
        fin = datetime.strptime(plazo_fin, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (fin - (hoy or date.today())).days
