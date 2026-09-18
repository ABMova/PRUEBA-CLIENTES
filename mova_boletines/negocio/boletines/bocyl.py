"""BOCYL - Boletin Oficial de Castilla y Leon.

VIA DE ACCESO: HTML del sumario diario. El BOCYL ofrece RSS (rss.do y
  rss.do?seccion=I..V) pero solo con las ultimas publicaciones y sin poder
  pedir una fecha concreta, asi que para el proceso diario se usa el sumario.
  Sumario: https://bocyl.jcyl.es/boletin.do?fechaBoletin=DD/MM/AAAA
  Estructura dentro de div#resultados: h3 (seccion), h4 (apartado),
  h5.encabezado6 (organismo), p (titulo), ul.descargaBoletin li a (PDF).
COMPROBADO: 17/09/2026 (sumario del 16/09/2026 con seccion I.C. Subvenciones).
SI CAMBIA: abrir el sumario y revisar el bloque div#resultados; el patron de
  los PDF es /boletines/AAAA/MM/DD/pdf/BOCYL-D-DDMMAAAA-N.pdf
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from negocio.boletines.base import PublicacionCruda, iso, iso_desde, pedir

CODIGO = "BOCYL"
NOMBRE = "Boletin Oficial de Castilla y Leon"
COMUNIDAD = "Castilla y Leon"
URL_COMPROBADA = "https://bocyl.jcyl.es/boletin.do?fechaBoletin=DD/MM/AAAA"
FECHA_COMPROBACION = "2026-09-17"

_BASE = "https://bocyl.jcyl.es"


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    url = f"{_BASE}/boletin.do?fechaBoletin={fecha:%d/%m/%Y}"
    respuesta = pedir(url)
    sopa = BeautifulSoup(respuesta.text, "html.parser")
    resultados = sopa.find(id="resultados")
    if resultados is None:
        return []

    publicaciones: list[PublicacionCruda] = []
    seccion = ""
    apartado = ""
    organismo = ""
    marca_dia = fecha.strftime("%d%m%Y")

    for nodo in resultados.find_all(["h3", "h4", "h5", "p", "ul"]):
        if nodo.name == "h3":
            seccion = nodo.get_text(" ", strip=True)
            apartado = ""
            continue
        if nodo.name == "h4":
            apartado = nodo.get_text(" ", strip=True)
            continue
        if nodo.name == "h5":
            organismo = nodo.get_text(" ", strip=True)
            continue
        if nodo.name == "p":
            titulo = nodo.get_text(" ", strip=True)
            if titulo:
                publicaciones.append(PublicacionCruda(
                    codigo_boletin=CODIGO,
                    titulo=titulo,
                    organismo=organismo,
                    seccion=f"{seccion} / {apartado}".strip(" /"),
                    url_oficial=url,
                    url_pdf="",
                    fecha=iso(fecha),
                    texto=titulo,
                ))
            continue
        # ul.descargaBoletin: enlaces de la ultima publicacion anadida
        if "descargaBoletin" in (nodo.get("class") or []) and publicaciones:
            enlace = nodo.find("a", href=True)
            if enlace:
                destino = enlace["href"]
                if not destino.startswith("http"):
                    destino = f"{_BASE}/{destino.lstrip('/')}"
                publicaciones[-1].url_pdf = destino
                fecha_pdf = re.search(r"BOCYL-D-(\d{8})-", destino)
                if fecha_pdf:
                    # La fecha del PDF manda: si fuera de otro dia, el orquestador la descarta.
                    publicaciones[-1].fecha = iso_desde(fecha_pdf.group(1), "%d%m%Y", fecha)
                identificador = re.search(rf"(BOCYL-D-{marca_dia}-[\d-]+)", destino)
                if identificador:
                    publicaciones[-1].identificador = identificador.group(1)
                    publicaciones[-1].url_oficial = destino.replace("/pdf/", "/html/").replace(
                        ".pdf", ".do")
    return [p for p in publicaciones if p.titulo]
