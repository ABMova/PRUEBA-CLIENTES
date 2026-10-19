"""Localiza y descarga las normas que cita una convocatoria.

Un extracto no se explica solo: remite a sus bases reguladoras y, a veces, a
una modificacion posterior que ha cambiado precisamente el plazo o la cuantia.
Asi se cita de verdad (BORM 19/10/2026, bodegas de las rutas del vino):

    "conforme a las bases reguladoras previstas en la Orden de 2 de junio de
    2025, de la Consejeria de Turismo, Cultura, Juventud y Deportes, (BORM
    N.130 de 7 de junio 2025), modificada por la Orden de 9 de abril de 2026
    (BORM N. 86, del 16 de abril de 2026)"

La cita trae el boletin y el DIA EXACTO de publicacion, asi que no hace falta
un buscador por cada boletin: se pide a su adaptador el sumario de ese dia y se
busca dentro el anuncio que corresponde a la norma citada.

Para elegir el anuncio se pesan las palabras por lo raras que son ESE DIA: en
un sumario lleno de "orden", "consejeria" y "subvenciones", lo que distingue a
la norma buscada es "bodegas", "turismo" o "modifica". Medido en los dos casos
de arriba, la acertada saca 1,00 y 0,84 y la siguiente candidata 0,14 y 0,22.

Si ninguna destaca con claridad no se descarga nada y la cita se le pasa al
modelo como hasta ahora: mejor sin las bases que con las bases equivocadas.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import date
from typing import NamedTuple

from negocio import boletines
from negocio.boletines.base import ErrorBoletin, PublicacionCruda, descargar_de_boletin
from negocio.extraccion import normalizar
from negocio.plazos import MESES

registro = logging.getLogger(__name__)

# Como se nombra cada boletin cuando se le cita. El DOGV se llamo DOCV hasta
# 2016 y las bases antiguas se siguen citando con el nombre de entonces.
BOLETINES = {"BOE": "BOE", "BORM": "BORM", "BOJA": "BOJA", "BOCM": "BOCM",
             "DOGC": "DOGC", "DOGV": "DOGV", "DOCV": "DOGV", "DOCM": "DOCM"}

# Tipos de norma que aprueban o cambian unas bases.
_TIPOS = r"(?:Orden|Resoluci[oó]n|Real\s+Decreto|Decreto(?:\s+Ley)?|Acuerdo|Ley|Instrucci[oó]n)"
_INICIO_NORMA = re.compile(_TIPOS + r"\b", re.IGNORECASE)

# "(BORM N.130 de 7 de junio 2025)", "(DOGV num. 9876, de 3 de marzo de 2025)"
_CITA = re.compile(
    r"\b(" + "|".join(BOLETINES) + r")\b"
    r"[^)\n0-9]{0,20}"                   # " n.", " num. ", ", de "
    r"(?:(\d{1,4})[^)\n0-9]{1,15})?"     # numero del boletin, cuando lo dice
    r"(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")"
    r"(?:\s*(?:de|del)?\s*(\d{4}))?",
    re.IGNORECASE)

# Lo que le da sentido a la cita. Sin uno de estos papeles no se descarga nada:
# una convocatoria cita media docena de leyes generales que no aportan al
# resumen y cada una costaria una llamada y unos miles de caracteres.
_PAPELES = (
    ("modificacion", re.compile(r"modificad|modificaci[oó]n|se\s+modifica", re.IGNORECASE)),
    ("ampliacion", re.compile(r"ampliaci[oó]n|se\s+ampl[ií]a|pr[oó]rroga", re.IGNORECASE)),
    ("bases reguladoras", re.compile(r"bases\s+reguladoras|bases\s+que\s+regulan", re.IGNORECASE)),
)
# La convocatoria no se busca aqui a proposito: cuando existe la da la BDNS con
# su codigo, y aceptar ese papel traia convocatorias ajenas que el texto nombra
# de pasada ("en los mismos terminos que la convocatoria de 2026").

# Normas generales: se citan en casi todas las convocatorias y nunca dicen nada
# de ESTA ayuda. Aunque el contexto hable de bases, no se descargan.
_GENERALES = re.compile(
    r"\b(38/2003|887/2006|39/2015|40/2015|19/2013|9/2017|58/2003|47/2003|1/2004"
    r"|2023/2831|2023/2832|651/2014|1/2016|2/2004)\b"
    r"|general\s+de\s+subvenciones|procedimiento\s+administrativo\s+com[uú]n"
    r"|r[eé]gimen\s+jur[ií]dico\s+del\s+sector\s+p[uú]blico|protecci[oó]n\s+de\s+datos"
    r"|contratos\s+del\s+sector\s+p[uú]blico|haciendas\s+locales", re.IGNORECASE)

# La cita se busca hacia atras desde el parentesis del boletin. Mas lejos de
# esto ya no es la misma frase.
_ALCANCE_ATRAS = 400

ACIERTO_MINIMO = 0.50      # por debajo, no se da por encontrada
VENTAJA_MINIMA = 0.15      # y tiene que destacar sobre la siguiente candidata

_VACIAS = {"de", "del", "la", "las", "el", "los", "por", "que", "para", "con", "una", "uno",
           "en", "se", "al", "lo", "como", "mediante", "sobre", "cual", "esta", "este",
           "anuncio", "extracto", "num", "numero"}

# El orden en que se gastan el presupuesto de texto y las descargas: una
# modificacion son dos paginas y puede haber cambiado el plazo; las bases son
# largas pero son donde estan los gastos subvencionables.
_PRIORIDAD = {"modificacion": 0, "ampliacion": 1, "bases reguladoras": 2}


class Referencia(NamedTuple):
    """Una norma citada en el texto, con donde se publico."""

    papel: str           # modificacion | ampliacion | bases reguladoras | convocatoria
    cita: str            # el texto de la cita, tal como aparece
    boletin: str         # codigo del adaptador (BORM, BOE...)
    fecha: date          # dia en que se publico en ese boletin
    numero: str = ""

    @property
    def descripcion(self) -> str:
        numero = f" n.º {self.numero}" if self.numero else ""
        return f"{self.papel.capitalize()} ({self.boletin}{numero} de {self.fecha:%d/%m/%Y})"


def referencias(texto: str) -> list[Referencia]:
    """Normas citadas en el texto que se pueden ir a buscar a su boletin."""
    # En un PDF la cita llega partida ("(BORM n. 86, del 16 de abril\nde 2026)"),
    # asi que se busca sobre el texto en una sola linea.
    texto = " ".join((texto or "").split())
    encontradas: list[Referencia] = []
    vistas: set[tuple] = set()
    for cita in _CITA.finditer(texto):
        nombre, numero, dia, mes, ano = cita.groups()
        boletin = BOLETINES[nombre.upper()]
        if boletin not in boletines.ADAPTADORES:
            continue  # boletin que ya no se vigila

        contexto = texto[max(0, cita.start() - _ALCANCE_ATRAS):cita.start()]
        inicios = list(_INICIO_NORMA.finditer(contexto))
        if not inicios:
            continue
        citada = contexto[inicios[-1].start():].strip(" ,;(")
        # Solo se mira la norma citada: casi todo extracto nombra la Ley 38/2003
        # unas lineas antes de remitir a sus bases, y eso no la descalifica.
        if _GENERALES.search(citada):
            continue

        papel = _papel_de(contexto, citada)
        if not papel:
            continue

        publicada = _fecha(dia, mes, ano, citada)
        if not publicada:
            continue
        huella = (boletin, publicada, papel)
        if huella in vistas:
            continue
        vistas.add(huella)
        encontradas.append(Referencia(papel, " ".join(citada.split())[:300],
                                      boletin, publicada, numero or ""))

    encontradas.sort(key=lambda r: _PRIORIDAD.get(r.papel, 9))
    return encontradas


def _papel_de(contexto: str, citada: str) -> str:
    """Para que se cita la norma. Cadena vacia si no se ve claro."""
    # El contexto inmediato manda sobre el texto de la propia norma: "modificada
    # por la Orden de..." es una modificacion aunque la Orden hable de bases.
    for papel, patron in _PAPELES:
        if patron.search(contexto[-250:]):
            return papel
    for papel, patron in _PAPELES:
        if patron.search(citada):
            return papel
    return ""


def _fecha(dia: str, mes: str, ano: str | None, citada: str) -> date | None:
    """Fecha de publicacion en el boletin. El ano puede faltar en la cita."""
    anos = [int(ano)] if ano else []
    if not anos:
        # "BORM n. 86, del 16 de abril": el ano es el de la propia norma.
        anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", citada)][-1:]
    for candidato in anos:
        try:
            return date(candidato, MESES[mes.lower()], int(dia))
        except (ValueError, KeyError):
            continue
    return None


def localizar(referencia: Referencia) -> PublicacionCruda | None:
    """El anuncio del sumario que corresponde a la norma citada, si se acierta."""
    try:
        anuncios = _sumario(referencia.boletin, referencia.fecha)
    except ErrorBoletin as error:
        registro.warning("No se pudo leer el %s del %s: %s",
                         referencia.boletin, referencia.fecha, error)
        return None
    if not anuncios:
        registro.info("El %s del %s no trae anuncios: no se localiza %s",
                      referencia.boletin, referencia.fecha, referencia.papel)
        return None

    notas = sorted(_notas(referencia.cita, _sin_repetidos(anuncios)),
                   key=lambda par: par[0], reverse=True)
    mejor, candidata = notas[0]
    segunda = notas[1][0] if len(notas) > 1 else 0.0
    if mejor < ACIERTO_MINIMO or mejor - segunda < VENTAJA_MINIMA:
        registro.info("Ninguna candidata clara para %s en el %s del %s (%.2f frente a %.2f)",
                      referencia.papel, referencia.boletin, referencia.fecha, mejor, segunda)
        return None
    registro.info("%s localizada en el %s del %s con nota %.2f: %s",
                  referencia.papel, referencia.boletin, referencia.fecha, mejor,
                  candidata.titulo[:100])
    return candidata


def _sin_repetidos(anuncios: list[PublicacionCruda]) -> list[PublicacionCruda]:
    """Un sumario puede traer el mismo anuncio dos veces (una por seccion).

    Importa porque dos copias con la misma nota se anularian la una a la otra al
    exigir que la mejor destaque sobre la segunda.
    """
    unicos: dict[tuple, PublicacionCruda] = {}
    for anuncio in anuncios:
        unicos.setdefault((anuncio.titulo.strip(), anuncio.url_pdf), anuncio)
    return list(unicos.values())


def _notas(cita: str, anuncios: list[PublicacionCruda]) -> list[tuple[float, PublicacionCruda]]:
    """Parecido de la cita con cada anuncio, pesando las palabras raras del dia."""
    frecuencia: Counter = Counter()
    for anuncio in anuncios:
        frecuencia.update(_palabras(f"{anuncio.titulo} {anuncio.organismo}"))
    total = len(anuncios)

    def peso(palabra: str) -> float:
        return math.log(total / (1 + frecuencia.get(palabra, 0))) + 0.2

    buscadas = _palabras(cita)
    techo = sum(peso(p) for p in buscadas) or 1.0
    return [(sum(peso(p) for p in buscadas & _palabras(f"{a.titulo} {a.organismo}")) / techo, a)
            for a in anuncios]


def _palabras(texto: str) -> set[str]:
    """Raices de las palabras que distinguen un titulo.

    Se cortan a seis letras para que "modificada" y "modifica" o "reguladoras"
    y "reguladora" cuenten como la misma palabra.
    """
    sueltas = re.findall(r"[a-z0-9]+", normalizar(texto or ""))
    return {p[:6] for p in sueltas if len(p) >= 4 and p not in _VACIAS}


def _sumario(codigo: str, dia: date) -> list[PublicacionCruda]:
    """Sumario de un boletin, guardado por si se pide dos veces en la misma ejecucion."""
    guardado = _SUMARIOS.get((codigo, dia))
    if guardado is None:
        guardado = boletines.adaptador(codigo).obtener_publicaciones(dia)
        _SUMARIOS[(codigo, dia)] = guardado
    return guardado


_SUMARIOS: dict[tuple[str, date], list[PublicacionCruda]] = {}


def descargar(anuncio: PublicacionCruda) -> bytes | None:
    """PDF de un anuncio localizado en un sumario."""
    if not anuncio.url_pdf:
        return None
    try:
        respuesta = descargar_de_boletin(anuncio.url_pdf, anuncio.codigo_boletin)
    except ErrorBoletin as error:
        registro.warning("No se pudo descargar %s: %s", anuncio.url_pdf, error)
        return None
    return respuesta.content if respuesta.content[:5] == b"%PDF-" else None
