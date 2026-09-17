"""DOGC - Diari Oficial de la Generalitat de Catalunya (Cataluna).

VIA DE ACCESO: API REST JSON del EADOP. Ojo: el servicio esta en el dominio
  portaldogc.gencat.cat, NO en dogc.gencat.cat (ahi devuelve 404).
  Numero por fecha: POST https://portaldogc.gencat.cat/eadop-rest/api/dogc/calendarDOGC
                    (month=MM&year=AAAA&language=ca)  -> linkDOGC con numDOGC
  Sumario:          POST https://portaldogc.gencat.cat/eadop-rest/api/dogc/summaryDOGC
                    (numDOGC=NNNN&language=ca)
COMPROBADO: 17/09/2026 (calendario de septiembre y sumario 9500 correctos).
AVISO TLS: este servidor negocia cifrados antiguos y OpenSSL 3 los rechaza por
  defecto; por eso se pide con tls_legado=True (ver base._AdaptadorTLSLegado).
SI CAMBIA: abrir https://dogc.gencat.cat/ca/sumari-del-dogc/ y revisar el
  fichero fpca_sumari_DOGC.js; ahi estan la URI del servicio y sus parametros.
NOTA: se pide en catalan porque es el idioma en el que el servicio sirve
  siempre el sumario completo; el titulo se guarda tal cual se publica.
"""
from __future__ import annotations

from datetime import date

from negocio.boletines.base import ErrorBoletin, PublicacionCruda, iso, pedir

CODIGO = "DOGC"
NOMBRE = "Diari Oficial de la Generalitat de Catalunya"
COMUNIDAD = "Cataluna"
URL_COMPROBADA = "https://portaldogc.gencat.cat/eadop-rest/api/dogc/summaryDOGC"
FECHA_COMPROBACION = "2026-09-17"

_BASE = "https://portaldogc.gencat.cat/eadop-rest/api/dogc"
_IDIOMA = "ca"


def _numero_de(fecha: date) -> str | None:
    respuesta = pedir(f"{_BASE}/calendarDOGC", metodo="POST", tls_legado=True,
                      datos={"month": f"{fecha.month:02d}", "year": str(fecha.year),
                             "language": _IDIOMA})
    try:
        calendario = respuesta.json().get("calendar") or []
    except ValueError as error:
        raise ErrorBoletin(f"Respuesta no JSON del calendario del DOGC: {error}") from error

    buscada = fecha.strftime("%d/%m/%Y")
    for dia in calendario:
        if dia.get("date") == buscada and dia.get("hasDOGC"):
            enlace = dia.get("linkDOGC") or ""
            for parte in enlace.lstrip("?").split("&"):
                if parte.startswith("numDOGC="):
                    return parte.split("=", 1)[1]
    return None


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    numero = _numero_de(fecha)
    if numero is None:
        return []

    respuesta = pedir(f"{_BASE}/summaryDOGC", metodo="POST", tls_legado=True,
                      datos={"numDOGC": numero, "language": _IDIOMA})
    try:
        datos = respuesta.json()
    except ValueError as error:
        raise ErrorBoletin(f"Respuesta no JSON del sumario del DOGC: {error}") from error

    publicaciones: list[PublicacionCruda] = []
    for sumario in datos.get("sumaris") or []:
        for seccion in sumario.get("section") or []:
            nombre_seccion = (seccion.get("title") or "").strip()
            for cabecera in seccion.get("header") or []:
                organismo = (cabecera.get("title") or "").strip()
                for documento in cabecera.get("document") or []:
                    titulo = (documento.get("title") or "").strip()
                    if not titulo:
                        continue
                    url_pdf = documento.get("linkDownloadDocumentPDF") or ""
                    identificador = ""
                    if "documentId=" in url_pdf:
                        identificador = url_pdf.split("documentId=", 1)[1].split("&", 1)[0]
                    publicaciones.append(PublicacionCruda(
                        codigo_boletin=CODIGO,
                        titulo=titulo,
                        organismo=organismo,
                        seccion=nombre_seccion,
                        url_oficial=(f"https://dogc.gencat.cat/ca/document-del-dogc/"
                                     f"?documentId={identificador}" if identificador
                                     else f"https://dogc.gencat.cat/ca/sumari-del-dogc/?numDOGC={numero}"),
                        url_pdf=url_pdf,
                        fecha=iso(fecha),
                        texto=titulo,
                        identificador=identificador,
                        extra={"num_dogc": numero},
                    ))
    return publicaciones
