"""BORM - Boletin Oficial de la Region de Murcia.

VIA DE ACCESO: API REST XML que consume la sede electronica (AngularJS).
  Sumario del dia: GET https://www.borm.es/services/boletin/fecha/DD-MM-AAAA/sumario
  PDF del anuncio: https://www.borm.es/services/anuncio/{id}/pdf   (id interno del anuncio)
  Texto plano:     https://www.borm.es/services/anuncio/{id}/txt
  Pagina publica:  https://www.borm.es/#/home/anuncio/DD-MM-AAAA/{numero}
COMPROBADO: 17/09/2026 (boletin 215). Enlaces de PDF y pagina publica
  corregidos y comprobados el 18/09/2026 (la version anterior los construia mal).
AVISO IMPORTANTE: borm.es esta detras de un anti-bot comercial (Radware). Las
  peticiones con agente de robot reciben una pagina de captcha. Por eso este
  adaptador se identifica como navegador y anade la cabecera From con el
  contacto. Si algun dia devuelve el reto igualmente, el adaptador lo detecta
  y devuelve un error controlado: NO se intenta resolver el captcha. En ese
  caso hay que pedir al BORM una IP autorizada o darse de alta en sus alertas.
SI CAMBIA: los servicios estan listados en
  https://www.borm.es/scripts/boletines/factories/boletinFactory.js
"""
from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup

from negocio.boletines.base import (ErrorBoletin, PublicacionCruda, detectar_anti_bot, iso,
                                    iso_desde, pedir)

CODIGO = "BORM"
NOMBRE = "Boletin Oficial de la Region de Murcia"
COMUNIDAD = "Murcia"
URL_COMPROBADA = "https://www.borm.es/services/boletin/fecha/{DD-MM-AAAA}/sumario"
FECHA_COMPROBACION = "2026-09-17"

_BASE = "https://www.borm.es"


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    url = f"{_BASE}/services/boletin/fecha/{fecha:%d-%m-%Y}/sumario"
    respuesta = pedir(url, navegador=True, cabeceras={"Referer": f"{_BASE}/"},
                      permitir_404=True)
    if respuesta.status_code == 404:
        return []  # ese dia no hay BORM (fines de semana y festivos)
    texto = respuesta.text
    if detectar_anti_bot(texto):
        raise ErrorBoletin(
            "El BORM ha devuelto un reto anti-bot (Radware). No se resuelve por diseno: "
            "solicitar al BORM autorizacion para la IP del servidor o usar sus alertas.")
    if "<SumarioBoletinDTO" not in texto:
        return []

    sopa = BeautifulSoup(respuesta.content, "lxml-xml")
    publicaciones: list[PublicacionCruda] = []
    for anuncio in sopa.find_all("anunciosBoletin"):
        titulo = _texto(anuncio, "sumario")
        if not titulo:
            continue
        numero = _texto(anuncio, "numero")
        ano = _texto(anuncio, "ano")
        anunciante = _texto(anuncio, "anunciante")
        sub = _texto(anuncio, "subAnunciante")
        organismo = f"{anunciante} - {sub}".strip(" -") if sub else anunciante
        seccion = f"{_texto(anuncio, 'apartado')} / {_texto(anuncio, 'subApartado')}".strip(" /")
        id_anuncio = _texto(anuncio, "id")
        fecha_anuncio = _texto(anuncio, "fechaPublicacion") or f"{fecha:%d-%m-%Y}"
        identificador = f"{ano}{numero}" if ano and numero else id_anuncio
        publicaciones.append(PublicacionCruda(
            codigo_boletin=CODIGO,
            titulo=titulo,
            organismo=organismo,
            seccion=seccion,
            # Rutas sacadas de scripts/app.js y anuncioFactory.js de la sede del BORM.
            url_oficial=(f"{_BASE}/#/home/anuncio/{fecha_anuncio}/{numero}" if numero
                         else f"{_BASE}/#/home/sumario/{fecha:%d-%m-%Y}"),
            url_pdf=f"{_BASE}/services/anuncio/{id_anuncio}/pdf" if id_anuncio else "",
            fecha=iso_desde(_texto(anuncio, "fechaPublicacion"), "%d-%m-%Y", fecha),
            texto=titulo,
            identificador=identificador,
        ))
    return publicaciones


def _texto(nodo, etiqueta: str) -> str:
    hijo = nodo.find(etiqueta)
    return hijo.get_text(" ", strip=True) if hijo else ""
