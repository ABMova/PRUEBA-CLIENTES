"""DOCM - Diario Oficial de Castilla-La Mancha.

VIA DE ACCESO: HTML del sumario diario (no ofrece API ni RSS utilizables).
  Sumario: https://docm.castillalamancha.es/portaldocm/sumario.do?fecha=AAAAMMDD
  Estructura: div.categoriaDiario > h3.cabeceraCategoria (seccion)
              h4.tituloOrganismo (organismo)
              p.sumario > a[href*=descargarArchivo.do] (titulo + PDF)
              enlace HTML en el onclick de verArchivoHtml.do
COMPROBADO: 17/09/2026 (sumario del dia con sus disposiciones y PDF).
SI CAMBIA: abrir el sumario en el navegador y revisar las clases CSS de
  categoriaDiario / tituloOrganismo / sumario; son las tres unicas que se usan.
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from negocio.boletines.base import PublicacionCruda, iso, iso_desde, pedir

CODIGO = "DOCM"
NOMBRE = "Diario Oficial de Castilla-La Mancha"
COMUNIDAD = "Castilla-La Mancha"
URL_COMPROBADA = "https://docm.castillalamancha.es/portaldocm/sumario.do?fecha=AAAAMMDD"
FECHA_COMPROBACION = "2026-09-17"

_BASE = "https://docm.castillalamancha.es/portaldocm/"


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    url = f"{_BASE}sumario.do?fecha={fecha:%Y%m%d}"
    respuesta = pedir(url)
    respuesta.encoding = respuesta.encoding or "ISO-8859-1"
    sopa = BeautifulSoup(respuesta.text, "html.parser")

    publicaciones: list[PublicacionCruda] = []
    for categoria in sopa.select("div.categoriaDiario"):
        cabecera = categoria.select_one("h3.cabeceraCategoria")
        seccion = cabecera.get_text(" ", strip=True) if cabecera else ""
        organismo = ""
        for nodo in categoria.find_all(["h4", "div", "p"]):
            clases = nodo.get("class") or []
            if nodo.name == "h4" and "tituloOrganismo" in clases:
                organismo = nodo.get_text(" ", strip=True)
                continue
            if nodo.name != "p" or "sumario" not in clases:
                continue
            enlace = nodo.find("a", href=True)
            if enlace is None:
                continue
            titulo = nodo.get_text(" ", strip=True)
            if not titulo:
                continue
            url_pdf = _absoluta(enlace["href"])
            publicaciones.append(PublicacionCruda(
                codigo_boletin=CODIGO,
                titulo=titulo,
                organismo=organismo,
                seccion=seccion,
                url_oficial=_url_html(nodo) or url,
                url_pdf=url_pdf,
                fecha=_fecha_de_ruta(url_pdf, fecha),
                texto=titulo,
                identificador=_identificador(url_pdf),
            ))
    return publicaciones


def _absoluta(destino: str) -> str:
    destino = destino.replace("&amp;", "&").lstrip("./")
    return destino if destino.startswith("http") else f"{_BASE}{destino}"


def _url_html(nodo) -> str:
    """El DOCM ofrece la version HTML en un onclick del hermano anterior."""
    contenedor = nodo.parent
    if contenedor is None:
        return ""
    for elemento in contenedor.find_all("a", onclick=True):
        encontrado = re.search(r"verArchivoHtml\.do\?ruta=([^&']+)", elemento["onclick"])
        if encontrado:
            return f"{_BASE}verArchivoHtml.do?ruta={encontrado.group(1)}&tipo=rutaDocm"
    return ""


def _fecha_de_ruta(url_pdf: str, respaldo: date) -> str:
    """La ruta del PDF lleva la fecha: ruta=AAAA/MM/DD/pdf/..."""
    encontrado = re.search(r"ruta=(\d{4}/\d{2}/\d{2})/", url_pdf)
    return iso_desde(encontrado.group(1) if encontrado else "", "%Y/%m/%d", respaldo)


def _identificador(url_pdf: str) -> str:
    encontrado = re.search(r"(\d{4}_\d+)\.pdf", url_pdf)
    return encontrado.group(1) if encontrado else ""
