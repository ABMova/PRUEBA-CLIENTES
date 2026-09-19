"""BOE - Boletin Oficial del Estado.

VIA DE ACCESO: API de datos abiertos del BOE (JSON), sumario diario.
  Sumario: https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD
           (cabecera Accept: application/json)
  Estructura: data.sumario.diario[] (varios si hay numero extraordinario)
              > seccion[] (codigo, nombre)
              > departamento[] (nombre)
              > epigrafe[] > item[]   o directamente   item[]
              item: identificador (BOE-A-..., BOE-B-...), titulo,
                    url_pdf.texto, url_html
  Dia sin BOE (domingos): HTTP 404 con cuerpo XML.
COMPROBADO: 19/09/2026 (sumario del 18/09/2026: 128 disposiciones en 6 secciones).
SECCIONES QUE SE VIGILAN: el BOE publica mucho mas que un boletin autonomico.
  Las ayudas salen en I (reales decretos y ordenes de concesion directa), III
  (convocatorias y bases reguladoras) y V-B (extractos de la BDNS). Se dejan
  fuera II-A y II-B (nombramientos, oposiciones), IV (justicia), V-A
  (contratacion) y V-C (anuncios particulares).
SI CAMBIA: abrir la URL del sumario con Accept: application/json y revisar los
  nombres de campo de arriba. La documentacion esta en
  https://www.boe.es/datosabiertos/documentos/APIsumarioBOE.pdf
"""
from __future__ import annotations

from datetime import date

from negocio.boletines.base import ErrorBoletin, PublicacionCruda, iso_desde, pedir

CODIGO = "BOE"
NOMBRE = "Boletin Oficial del Estado"
COMUNIDAD = "Estatal (BOE)"
URL_COMPROBADA = "https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD"
FECHA_COMPROBACION = "2026-09-19"

SECCIONES = {"1", "3", "5B"}


def _lista(valor) -> list:
    """La API devuelve un objeto suelto cuando solo hay uno, y una lista si hay varios."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def obtener_publicaciones(fecha: date) -> list[PublicacionCruda]:
    url = f"https://www.boe.es/datosabiertos/api/boe/sumario/{fecha:%Y%m%d}"
    respuesta = pedir(url, cabeceras={"Accept": "application/json"}, permitir_404=True)
    if respuesta.status_code == 404:
        return []  # ese dia no hay BOE (domingos)
    try:
        sumario = respuesta.json()["data"]["sumario"]
    except (ValueError, KeyError, TypeError) as error:
        raise ErrorBoletin(f"El sumario del BOE no tiene el formato esperado: {error}") from error

    fecha_fuente = iso_desde(sumario.get("metadatos", {}).get("fecha_publicacion", ""),
                             "%Y%m%d", fecha)
    publicaciones: list[PublicacionCruda] = []
    vistos: set[str] = set()
    for diario in _lista(sumario.get("diario")):
        for seccion in _lista(diario.get("seccion")):
            if seccion.get("codigo") not in SECCIONES:
                continue
            nombre_seccion = seccion.get("nombre", "")
            for departamento in _lista(seccion.get("departamento")):
                organismo = departamento.get("nombre", "")
                elementos = [(None, item) for item in _lista(departamento.get("item"))]
                for epigrafe in _lista(departamento.get("epigrafe")):
                    elementos += [(epigrafe.get("nombre", ""), item)
                                  for item in _lista(epigrafe.get("item"))]
                for epigrafe, item in elementos:
                    identificador = item.get("identificador", "")
                    titulo = (item.get("titulo") or "").strip()
                    if not titulo or identificador in vistos:
                        continue
                    vistos.add(identificador)
                    pdf = item.get("url_pdf")
                    publicaciones.append(PublicacionCruda(
                        codigo_boletin=CODIGO,
                        titulo=titulo,
                        organismo=organismo,
                        seccion=f"{nombre_seccion} - {epigrafe}" if epigrafe else nombre_seccion,
                        url_oficial=item.get("url_html") or (
                            f"https://www.boe.es/diario_boe/txt.php?id={identificador}"),
                        url_pdf=pdf.get("texto", "") if isinstance(pdf, dict) else (pdf or ""),
                        fecha=fecha_fuente,
                        texto=titulo,
                        identificador=identificador,
                    ))
    return publicaciones
