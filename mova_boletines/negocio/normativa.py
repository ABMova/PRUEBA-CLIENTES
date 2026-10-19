"""Reune toda la normativa de una ayuda antes de resumirla.

Lo que publica el boletin suele ser un EXTRACTO de media pagina que remite al
texto completo. Si el resumen se hace solo con eso, sale lleno de "se establece
en la correspondiente convocatoria": el plazo, los gastos y las cuantias estan
en la convocatoria entera y en las bases reguladoras, no en el extracto.

Este modulo busca los documentos que faltan y los devuelve para analizarlos
juntos, por dos vias:

  1. La Base de Datos Nacional de Subvenciones. El extracto cita su codigo
     BDNS, y con el se consigue la ficha oficial (plazo, presupuesto,
     beneficiarios, regimen) y el PDF integro de la convocatoria.
  2. Las normas que cita el propio texto: las bases reguladoras y, cuando las
     hay, la modificacion o la ampliacion que las cambio despues. La cita trae
     el boletin y el dia, asi que se van a buscar a su sumario (negocio/normas).

El texto anadido se paga al modelo, asi que hay presupuesto para cada via y un
orden: primero la convocatoria, luego las modificaciones (dos paginas que
pueden haber cambiado el plazo) y al final las bases, que son las mas largas.

Nunca falla hacia arriba: si una fuente no responde o no se localiza, el
resumen se hace con lo que haya, como hasta ahora.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

from datos import repositorio
from integraciones import bdns
from negocio import normas
from negocio.extraccion import texto_con_paginas

registro = logging.getLogger(__name__)

# Topes de texto anadido a la publicacion. Una convocatoria entera ronda los
# 110.000 caracteres y unas bases reguladoras los 40.000.
LIMITE_CONVOCATORIA = 200_000
LIMITE_NORMAS = 120_000

# Un PDF sin texto (escaneado) no aporta nada al resumen.
MINIMO_UTIL = 500

MAXIMO_NORMAS = 3

# Por encima de esto, lo publicado no es un extracto: son las bases enteras (la
# Orden JUI/1097/2026 del BOE ocupa 13 paginas y 50.000 caracteres). Entonces no
# hay nada que ir a buscar, y barrer solo traia normas que el texto nombra de
# pasada.
EXTRACTO_MAXIMO = 20_000


class Fuente(NamedTuple):
    """Un documento que se le pasa al modelo, con su procedencia."""

    titulo: str
    texto: str
    url: str = ""
    paginas: int = 0


class Normativa(NamedTuple):
    fuentes: list[Fuente]
    datos_bdns: dict
    referencias: list[str]     # normas citadas que no se han podido descargar

    @property
    def hay(self) -> bool:
        return bool(self.fuentes or self.datos_bdns)


def reunir(publicacion: dict, texto_publicacion: str) -> Normativa:
    """Documentos y datos oficiales relacionados con esta ayuda.

    Se puede apagar desde Ajustes: con `normativa_activa` a 0 el resumen se
    hace solo con lo publicado, que cuesta una decima parte.
    """
    if repositorio.ajuste("normativa_activa", "1") != "1":
        registro.info("Normativa desactivada en Ajustes: se resume solo lo publicado")
        return Normativa([], {}, [])

    fuentes: list[Fuente] = []
    datos = _ficha_bdns(publicacion, texto_publicacion)
    if datos:
        fuentes.extend(_convocatoria(datos))
    hay_convocatoria = bool(fuentes)

    # Las bases se citan en el extracto, pero tambien (y mejor) en el texto
    # completo de la convocatoria, que es donde se detalla a que norma remite.
    texto_citas = "\n".join([texto_publicacion] + [f.texto for f in fuentes])
    citadas = normas.referencias(texto_citas)
    halladas, pendientes = _descargar_normas(citadas)
    fuentes.extend(halladas)

    # Lo que queda: normas citadas sin decir donde se publicaron. Localizarlas
    # cuesta barrer los sumarios de varios dias, asi que solo se hace cuando el
    # resumen se quedaria con el extracto y nada mas.
    if not hay_convocatoria and not halladas and len(texto_publicacion) < EXTRACTO_MAXIMO:
        a_ciegas, sin_localizar = _barrer_normas(publicacion, texto_publicacion, citadas)
        fuentes.extend(a_ciegas)
        pendientes.extend(sin_localizar)

    return Normativa(fuentes, datos, pendientes)


def _ficha_bdns(publicacion: dict, texto: str) -> dict:
    codigo = bdns.codigo_en(texto) or bdns.codigo_en(publicacion.get("titulo", ""))
    if not codigo:
        return {}
    datos = bdns.ficha(codigo)
    if not datos:
        registro.info("La ayuda cita el codigo BDNS %s pero no se ha podido consultar", codigo)
        return {}
    return datos


def _convocatoria(datos: dict) -> list[Fuente]:
    """El PDF integro de la convocatoria, segun la BDNS."""
    codigo = datos.get("codigoBDNS", "")
    fuentes: list[Fuente] = []
    anadido = 0
    for documento in bdns.documentos(datos)[:2]:
        contenido = bdns.descargar(documento["id"])
        if not contenido:
            continue
        texto, paginas, _ = texto_con_paginas(contenido)
        texto = _recortar(texto, LIMITE_CONVOCATORIA - anadido)
        if not texto:
            break
        anadido += len(texto)
        fuentes.append(Fuente(
            titulo=f"{documento.get('descripcion') or 'Documento de la convocatoria'} "
                   f"(BDNS {codigo})",
            texto=texto,
            url=bdns.URL_PUBLICA.format(codigo=codigo),
            paginas=paginas))
    registro.info("BDNS %s: %d documento(s) de la convocatoria", codigo, len(fuentes))
    return fuentes


def _barrer_normas(publicacion: dict, texto: str, citadas) -> tuple[list[Fuente], list[str]]:
    """Las bases que no dicen donde se publicaron, buscadas por los sumarios.

    Solo se barre UNA, la de mas valor segun el orden de papeles: cada barrido
    son hasta treinta consultas al boletin, y hacer tres multiplicaria el
    trafico contra una web que no es nuestra.
    """
    if repositorio.ajuste("normativa_barrido", "1") != "1":
        return [], []
    sueltas = normas.sin_publicacion(texto, str(publicacion.get("codigo_boletin") or ""), citadas)
    if not sueltas:
        return [], []
    dias = repositorio.ajuste_int("dias_barrido_normas", normas.DIAS_BARRIDO)
    return _descargar_normas(sueltas[:1], dias)


def _descargar_normas(referencias, dias_barrido: int = 0) -> tuple[list[Fuente], list[str]]:
    """Baja el PDF de cada norma localizada y deja apuntadas las que no."""
    fuentes: list[Fuente] = []
    pendientes: list[str] = []
    anadido = 0
    for referencia in list(referencias)[:MAXIMO_NORMAS]:
        anuncio = (normas.localizar(referencia, dias_barrido) if dias_barrido
                   else normas.localizar(referencia))
        contenido = normas.descargar(anuncio) if anuncio else None
        if not contenido:
            pendientes.append(f"{referencia.descripcion}: {referencia.cita}")
            continue
        cuerpo, paginas, _ = texto_con_paginas(contenido)
        cuerpo = _recortar(cuerpo, LIMITE_NORMAS - anadido)
        if not cuerpo:
            pendientes.append(f"{referencia.descripcion}: {referencia.cita}")
            continue
        anadido += len(cuerpo)
        fuentes.append(Fuente(
            titulo=f"{_descripcion(referencia, anuncio)} — {anuncio.titulo[:110]}",
            texto=cuerpo,
            url=anuncio.url_oficial or anuncio.url_pdf,
            paginas=paginas))
    return fuentes, pendientes


def _recortar(texto: str, disponible: int) -> str:
    """El texto que cabe en lo que queda de presupuesto, o nada si no cabe."""
    if len(texto) < MINIMO_UTIL:
        return ""
    if len(texto) > disponible:
        texto = texto[:max(0, disponible)]
    return texto if len(texto) >= MINIMO_UTIL else ""


def resumen_oficial(datos: dict) -> str:
    """Los datos de la ficha de la BDNS, para que el modelo no los invente."""
    if not datos:
        return ""
    frase_plazo, fecha_fin = bdns.plazo_de(datos)
    lineas = [
        f"Codigo BDNS: {datos.get('codigoBDNS', '')}",
        f"Organo: {' / '.join(v for v in (datos.get('organo') or {}).values() if v)}",
        f"Presupuesto total: {datos.get('presupuestoTotal', '')}",
        f"Tipo de convocatoria: {datos.get('tipoConvocatoria', '')}",
        f"Beneficiarios: {', '.join(b.get('descripcion', '') for b in datos.get('tiposBeneficiarios') or [])}",
        f"Sectores: {', '.join(s.get('descripcion', '') for s in datos.get('sectores') or [])}",
        f"Regimen de ayudas: {(datos.get('reglamento') or {}).get('descripcion', '')}",
        f"Bases reguladoras: {datos.get('descripcionBasesReguladoras', '')}",
        f"Inicio del plazo: {datos.get('fechaInicioSolicitud') or datos.get('textInicio') or ''}",
        f"Fin del plazo: {fecha_fin or frase_plazo or ''}",
    ]
    return "\n".join(linea for linea in lineas if linea.split(": ", 1)[1].strip())


def _descripcion(referencia, anuncio) -> str:
    """Como se nombra la norma en la lista de normativa analizada.

    Cuando se ha localizado barriendo, la referencia no sabia el dia: lo pone
    el anuncio que se ha encontrado.
    """
    if referencia.fecha or not anuncio.fecha:
        return referencia.descripcion
    dia = anuncio.fecha[8:10], anuncio.fecha[5:7], anuncio.fecha[:4]
    return (f"{referencia.papel.capitalize()} "
            f"({referencia.boletin} de {dia[0]}/{dia[1]}/{dia[2]})")
