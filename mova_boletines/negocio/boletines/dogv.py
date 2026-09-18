"""DOGV - Diari Oficial de la Generalitat Valenciana (Comunidad Valenciana).

VIA DE ACCESO: API REST JSON del portal (no documentada publicamente, pero es
la que consume la propia web del DOGV).
  Numero del dia:  GET https://dogv.gva.es/dogv-portal/dogv/latest?lang=es_es
                   GET https://dogv.gva.es/dogv-portal/dogv/anteriorYSiguiente?date=AAAA-MM-DD&lang=es_es
  Sumario:         GET https://dogv.gva.es/dogv-portal/dogv/{num}?lang=es_es&ordenSumario=1
  PDF:             https://dogv.gva.es/datos + urlPdf devuelto por el sumario
COMPROBADO: 17/09/2026 (sumario 10453, 30 disposiciones).
SI CAMBIA: abrir https://dogv.gva.es/es/inici (el sumario vive en un iframe
  /dogv-portal-frontend) y mirar en el inspector que peticiones hace a
  /dogv-portal/. La ruta del sumario es la unica que hace falta.
"""
from __future__ import annotations

from datetime import date, timedelta

from negocio.boletines.base import ErrorBoletin, PublicacionCruda, iso, iso_desde, pedir

CODIGO = "DOGV"
NOMBRE = "Diari Oficial de la Generalitat Valenciana"
COMUNIDAD = "Comunidad Valenciana"
URL_COMPROBADA = "https://dogv.gva.es/dogv-portal/dogv/{num}?lang=es_es&ordenSumario=1"
FECHA_COMPROBACION = "2026-09-17"

_BASE = "https://dogv.gva.es/dogv-portal"
_BASE_PDF = "https://dogv.gva.es/datos"


def _numero_de(fecha: date) -> int | None:
    """Numero de DOGV publicado en esa fecha, o None si no hubo boletin."""
    siguiente = fecha + timedelta(days=1)
    respuesta = pedir(f"{_BASE}/dogv/anteriorYSiguiente?date={iso(siguiente)}&lang=es_es")
    datos = respuesta.json()
    if datos.get("fechaDogvAnterior") == iso(fecha):
        return int(datos["numeroDogvAnterior"])

    # La fecha consultada puede no tener boletin: el servicio devuelve entonces
    # el anterior publicado. Se confirma contra el ultimo publicado.
    ultimo = pedir(f"{_BASE}/dogv/latest?lang=es_es").json()
    cabecera = ultimo.get("cabecera") or {}
    if _fecha_sumario(ultimo) == iso(fecha):
        return int(cabecera.get("numeroDogv"))
    return None


def _fecha_sumario(sumario: dict) -> str:
    bruta = (sumario.get("fechaSumario") or "").strip()
    if bruta and len(bruta) >= 10 and bruta[2] == "/":
        dia, mes, ano = bruta[:10].split("/")
        return f"{ano}-{mes}-{dia}"
    disposiciones = sumario.get("disposiciones") or []
    if disposiciones:
        publicada = (disposiciones[0].get("fechaPublicacion") or "")
        if len(publicada) == 10:
            dia, mes, ano = publicada.split("/")
            return f"{ano}-{mes}-{dia}"
    return ""


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    numero = _numero_de(fecha)
    if numero is None:
        return []

    respuesta = pedir(f"{_BASE}/dogv/{numero}?lang=es_es&ordenSumario=1")
    try:
        sumario = respuesta.json()
    except ValueError as error:
        raise ErrorBoletin(f"Respuesta no JSON del DOGV: {error}") from error

    publicaciones: list[PublicacionCruda] = []
    for disposicion in sumario.get("disposiciones") or []:
        titulo = (disposicion.get("titulo") or "").strip()
        if not titulo:
            continue
        seccion = ((disposicion.get("seccion") or {}).get("descripcion") or "").strip()
        url_pdf = disposicion.get("urlPdf") or ""
        if url_pdf and not url_pdf.startswith("http"):
            url_pdf = f"{_BASE_PDF}{url_pdf}"
        identificador = str(disposicion.get("id") or disposicion.get("codigoInsercion") or "")
        publicaciones.append(PublicacionCruda(
            codigo_boletin=CODIGO,
            titulo=titulo,
            organismo=(disposicion.get("organismo") or "").strip(),
            seccion=seccion,
            url_oficial=f"https://dogv.gva.es/es/disposicio-canonica?sig={identificador}"
                        if identificador else f"https://dogv.gva.es/es/inici",
            url_pdf=url_pdf,
            fecha=iso_desde(disposicion.get("fechaPublicacion") or "", "%d/%m/%Y", fecha),
            texto=titulo,
            identificador=identificador,
            extra={"numero_dogv": numero},
        ))
    return publicaciones
