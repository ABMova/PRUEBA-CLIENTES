"""BOCM - Boletin Oficial de la Comunidad de Madrid.

VIA DE ACCESO: XML de sumario diario (formato oficial, muy estable).
  Numero del dia:  POST https://www.bocm.es/search-day-month  (field_date[date]=DD/MM/AAAA)
                   redirige a /boletin/bocm-AAAAMMDD-NNN
  Sumario XML:     https://www.bocm.es/boletin/CM_Boletin_BOCM/AAAA/MM/DD/BOCM-AAAAMMDDNNN.xml
COMPROBADO: 17/09/2026 (boletin 222; el XML del 16/09 traia 221 disposiciones).
SI CAMBIA: en la portada de www.bocm.es, el buscador por dia envia un POST a
  /search-day-month; la pagina de resultado enlaza el XML en <url_xml_sumario>.
NOTA: el XML del sumario pesa varios MB porque incluye el texto completo de
  cada disposicion; por eso no hace falta descargar los PDF salvo excepciones.
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from negocio.boletines.base import ErrorBoletin, PublicacionCruda, iso, iso_desde, pedir

CODIGO = "BOCM"
NOMBRE = "Boletin Oficial de la Comunidad de Madrid"
COMUNIDAD = "Madrid"
URL_COMPROBADA = "https://www.bocm.es/boletin/CM_Boletin_BOCM/{a}/{m}/{d}/BOCM-{aaaammdd}{num}.xml"
FECHA_COMPROBACION = "2026-09-17"

_BUSCADOR = "https://www.bocm.es/search-day-month"


def _numero_de(fecha: date) -> str | None:
    respuesta = pedir(_BUSCADOR, metodo="POST",
                      datos={"field_date[date]": fecha.strftime("%d/%m/%Y")})
    encontrado = re.search(r"/boletin/bocm-(\d{8})-(\d+)", respuesta.url or "")
    if encontrado and encontrado.group(1) == fecha.strftime("%Y%m%d"):
        return encontrado.group(2)
    encontrado = re.search(rf"/boletin/bocm-{fecha:%Y%m%d}-(\d+)", respuesta.text)
    return encontrado.group(1) if encontrado else None


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    numero = _numero_de(fecha)
    if numero is None:
        return []

    url = (f"https://www.bocm.es/boletin/CM_Boletin_BOCM/{fecha:%Y/%m/%d}/"
           f"BOCM-{fecha:%Y%m%d}{numero}.xml")
    respuesta = pedir(url)
    sopa = BeautifulSoup(respuesta.content, "lxml-xml")
    if sopa.find("sumario") is None:
        raise ErrorBoletin("El XML de sumario del BOCM no tiene la estructura esperada")

    # Se recorren las disposiciones UNA vez y se sube por el arbol a buscar su
    # organismo, apartado y seccion. Con bucles anidados (seccion > apartado >
    # organismo > disposicion) y el find_all recursivo de BeautifulSoup, cada
    # disposicion salia repetida decenas de veces: 61 reales se convertian en
    # 1891. El identificador (BOCM-AAAAMMDD-N) evita cualquier repeticion.
    publicaciones: list[PublicacionCruda] = []
    vistos: set[str] = set()

    for disposicion in sopa.find_all("disposicion"):
        titulo = _texto(disposicion, "titulo")
        if not titulo:
            continue
        identificador = _texto(disposicion, "identificador")
        if identificador and identificador in vistos:
            continue
        if identificador:
            vistos.add(identificador)

        organismo = disposicion.find_parent("organismo")
        apartado = disposicion.find_parent("apartado")
        seccion = disposicion.find_parent("seccion")
        nombre_seccion = seccion.get("nombre", "") if seccion else ""
        nombre_apartado = apartado.get("nombre", "") if apartado else ""

        publicaciones.append(PublicacionCruda(
            codigo_boletin=CODIGO,
            titulo=titulo,
            organismo=organismo.get("nombre", "").strip() if organismo else "",
            seccion=f"{nombre_seccion} / {nombre_apartado}".strip(" /"),
            url_oficial=_texto(disposicion, "url_html"),
            url_pdf=_texto(disposicion, "url_pdf"),
            # El identificador lleva la fecha: BOCM-AAAAMMDD-N.
            fecha=iso_desde(identificador[5:13], "%Y%m%d", fecha),
            texto=_texto(disposicion, "texto") or titulo,
            identificador=identificador,
            extra={"numero_bocm": numero, "rango": _texto(disposicion, "rango")},
        ))
    return publicaciones


def _texto(nodo, etiqueta: str) -> str:
    hijo = nodo.find(etiqueta)
    return hijo.get_text(" ", strip=True) if hijo else ""
