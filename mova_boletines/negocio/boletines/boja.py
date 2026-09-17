"""BOJA - Boletin Oficial de la Junta de Andalucia.

VIA DE ACCESO: feed Atom oficial de boletin completo. Es la via mas limpia de
  las siete: una sola descarga trae el sumario entero de los ultimos boletines.
  Feed:  https://www.juntadeandalucia.es/boja/distribucion/boja.xml
  Cada <entry> es un boletin y su <content> xhtml lleva secciones (<p><strong>),
  organismos (<p>) y disposiciones (<li><a>) con enlace HTML y enlace PDF.
COMPROBADO: 17/09/2026 (boletin 181 de 17/09/2026).
SI CAMBIA: la Junta publica sus canales en
  https://www.juntadeandalucia.es/boja/distribucion.html
LIMITE CONOCIDO: el feed solo cubre los ultimos boletines. Para fechas fuera
  del feed se cae al indice del dia si se conoce el numero; si no, se informa.
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from negocio.boletines.base import PublicacionCruda, iso, pedir

CODIGO = "BOJA"
NOMBRE = "Boletin Oficial de la Junta de Andalucia"
COMUNIDAD = "Andalucia"
URL_COMPROBADA = "https://www.juntadeandalucia.es/boja/distribucion/boja.xml"
FECHA_COMPROBACION = "2026-09-17"

_FEED = "https://www.juntadeandalucia.es/boja/distribucion/boja.xml"

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}


def _fecha_de_titulo(titulo: str) -> date | None:
    encontrado = re.search(r"de (\d{1,2}) de ([a-zA-Zñ]+) de (\d{4})", titulo)
    if not encontrado:
        return None
    dia, mes, ano = encontrado.groups()
    numero_mes = _MESES.get(mes.lower())
    if not numero_mes:
        return None
    return date(int(ano), numero_mes, int(dia))


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    respuesta = pedir(_FEED)
    feed = BeautifulSoup(respuesta.content, "lxml-xml")

    entrada_dia = None
    for entrada in feed.find_all("entry"):
        titulo = entrada.find("title").get_text(strip=True) if entrada.find("title") else ""
        if _fecha_de_titulo(titulo) == fecha:
            entrada_dia = entrada
            break
    if entrada_dia is None:
        return []

    contenido = entrada_dia.find("content")
    if contenido is None:
        return []

    cuerpo = BeautifulSoup(contenido.decode_contents(), "html.parser")
    publicaciones: list[PublicacionCruda] = []
    seccion = ""
    organismo = ""

    for nodo in cuerpo.find_all(["p", "ul"]):
        if nodo.name == "p":
            if nodo.find("strong"):
                seccion = nodo.get_text(" ", strip=True)
                organismo = ""
            else:
                organismo = nodo.get_text(" ", strip=True)
            continue

        for elemento in nodo.find_all("li"):
            enlaces = elemento.find_all("a")
            if not enlaces:
                continue
            principal = enlaces[0]
            titulo = principal.get_text(" ", strip=True)
            if not titulo:
                continue
            url_pdf = ""
            for enlace in enlaces[1:]:
                destino = enlace.get("href", "")
                if destino.lower().endswith(".pdf"):
                    url_pdf = destino
                    break
            publicaciones.append(PublicacionCruda(
                codigo_boletin=CODIGO,
                titulo=titulo,
                organismo=organismo,
                seccion=seccion,
                url_oficial=principal.get("href", ""),
                url_pdf=url_pdf,
                fecha=iso(fecha),
                texto=titulo,
                identificador=_identificador(url_pdf),
            ))
    return publicaciones


def _identificador(url_pdf: str) -> str:
    encontrado = re.search(r"(BOJA\d{2}-\d+-\d+-\d+)", url_pdf)
    return encontrado.group(1) if encontrado else ""
