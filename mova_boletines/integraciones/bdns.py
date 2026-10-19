"""Base de Datos Nacional de Subvenciones: la convocatoria completa.

Lo que publica un boletin suele ser un EXTRACTO: media pagina que remite "al
texto completo, que puede consultarse en la Base de Datos Nacional de
Subvenciones". Ahi estan los datos que faltan (plazo, beneficiarios, gastos,
cuantias) y el PDF integro de la convocatoria.

VIA DE ACCESO: API publica, sin clave.
  Ficha:      GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias?vpd=GE&numConv=NNNNNN
  Documento:  GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias/documentos?idDocumento=NNNNNNN
COMPROBADO: 19/10/2026 con la convocatoria 934908 (bodegas de las rutas del
  vino, Region de Murcia): ficha completa y PDF de 666 KB.

De la ficha interesan sobre todo "textFin" (la frase del plazo, que calcula
negocio/plazos) y "fechaFinSolicitud" (la fecha exacta, cuando la hay).
"""
from __future__ import annotations

import json
import logging
import re

from negocio.boletines.base import ErrorBoletin, pedir

registro = logging.getLogger(__name__)

_API = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias"
URL_PUBLICA = "https://www.infosubvenciones.es/bdnstrans/GE/es/convocatoria/{codigo}"

# "BDNS (Identif.): 934908", "BDNS: 934908", "BDNS 934908", "/convocatoria/934908"
_CODIGO = re.compile(r"BDNS\s*(?:\(Identif\.?\)\s*)?[:\s]\s*(\d{5,7})", re.IGNORECASE)
_CODIGO_EN_URL = re.compile(r"/convocatoria/(\d{5,7})")

# Un documento de la BDNS no deberia pasar de esto; si pesa mas, algo raro pasa.
MAXIMO_BYTES = 25 * 1024 * 1024


def codigo_en(texto: str) -> str | None:
    """Codigo BDNS citado en el texto de un extracto, si lo hay."""
    for patron in (_CODIGO, _CODIGO_EN_URL):
        encontrado = patron.search(texto or "")
        if encontrado:
            return encontrado.group(1)
    return None


def ficha(codigo: str) -> dict | None:
    """Datos de la convocatoria, o None si la BDNS no la tiene o no responde."""
    try:
        respuesta = pedir(f"{_API}?vpd=GE&numConv={codigo}",
                          cabeceras={"Accept": "application/json"})
    except ErrorBoletin as error:
        registro.warning("La BDNS no responde para la convocatoria %s: %s", codigo, error)
        return None
    try:
        datos = respuesta.json()
    except (ValueError, json.JSONDecodeError):
        registro.warning("La BDNS devolvio algo que no es JSON para %s", codigo)
        return None
    if isinstance(datos, list):
        datos = datos[0] if datos else None
    return datos if isinstance(datos, dict) and datos.get("codigoBDNS") else None


# Las comunidades con lengua propia suben la convocatoria dos veces, una en
# cada lengua ("Texto en castellano de la convocatoria" / "Texto en otra lengua
# de la convocatoria"). Analizar las dos es pagar dos veces lo mismo, y ademas
# aqui todo se redacta en castellano.
_OTRA_LENGUA = re.compile(r"otra\s+lengua|valencia|catal|gallego|galego|euskera|vasco|ingles",
                          re.IGNORECASE)


def documentos(datos: dict) -> list[dict]:
    """Documentos adjuntos de la convocatoria, el mas reciente primero."""
    lista = [d for d in (datos.get("documentos") or []) if d.get("id")]
    lista.sort(key=lambda d: str(d.get("datPublicacion") or ""), reverse=True)
    en_castellano = [d for d in lista if not _OTRA_LENGUA.search(d.get("descripcion") or "")]
    return en_castellano or lista  # si solo esta en la otra lengua, mejor eso que nada


def descargar(id_documento: int | str) -> bytes | None:
    """PDF de un documento de la convocatoria."""
    try:
        respuesta = pedir(f"{_API}/documentos?idDocumento={id_documento}")
    except ErrorBoletin as error:
        registro.warning("No se pudo bajar el documento %s de la BDNS: %s", id_documento, error)
        return None
    contenido = respuesta.content
    if not contenido.startswith(b"%PDF-") or len(contenido) > MAXIMO_BYTES:
        return None
    return contenido


def plazo_de(datos: dict) -> tuple[str, str]:
    """(frase del plazo, fecha ISO de fin si la BDNS la da)."""
    frase = (datos.get("textFin") or "").strip()
    fin = (datos.get("fechaFinSolicitud") or "").strip()
    return frase, fin
