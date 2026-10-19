"""Reune toda la normativa de una ayuda antes de resumirla.

Lo que publica el boletin suele ser un EXTRACTO de media pagina que remite al
texto completo. Si el resumen se hace solo con eso, sale lleno de "se establece
en la correspondiente convocatoria": el plazo, los gastos y las cuantias estan
en la convocatoria entera, no en el extracto.

Este modulo busca los documentos que faltan y los devuelve para analizarlos
juntos. Hoy por la via mas fiable, la Base de Datos Nacional de Subvenciones:
el extracto cita su codigo BDNS, y con el se consigue la ficha oficial (plazo,
presupuesto, beneficiarios, regimen) y el PDF integro de la convocatoria.

Las bases reguladoras citadas en el texto ("Orden de 2 de junio de 2025, BORM
n. 130") todavia no se descargan: haria falta un buscador por cada boletin. La
referencia se pasa al modelo para que al menos la cite.

Nunca falla hacia arriba: si la BDNS no responde o la ayuda no tiene codigo, el
resumen se hace con lo que haya, como hasta ahora.
"""
from __future__ import annotations

import logging
import re
from typing import NamedTuple

from integraciones import bdns
from negocio.extraccion import texto_con_paginas

registro = logging.getLogger(__name__)

# Tope de texto que se anade a la publicacion. Cada caracter se paga al modelo,
# y una convocatoria entera ronda los 110.000.
LIMITE_ANADIDO = 400_000

# "las bases reguladoras previstas en la Orden de 2 de junio de 2025 ... (BORM n. 130 de 7 de junio)"
_BASES = re.compile(
    r"(bases\s+reguladoras[^.;]{0,400}?"
    r"(?:Orden|Resoluci[oó]n|Decreto|Acuerdo|Ley)\s+[^.;]{0,200})", re.IGNORECASE | re.DOTALL)


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


def _referencias_a_bases(texto: str) -> list[str]:
    encontradas = []
    for trozo in _BASES.findall(texto or "")[:3]:
        limpio = " ".join(trozo.split())
        if limpio and limpio not in encontradas:
            encontradas.append(limpio[:300])
    return encontradas


def reunir(publicacion: dict, texto_publicacion: str) -> Normativa:
    """Documentos y datos oficiales relacionados con esta ayuda."""
    referencias = _referencias_a_bases(texto_publicacion)

    codigo = bdns.codigo_en(texto_publicacion) or bdns.codigo_en(publicacion.get("titulo", ""))
    if not codigo:
        return Normativa([], {}, referencias)

    datos = bdns.ficha(codigo)
    if not datos:
        registro.info("La ayuda cita el codigo BDNS %s pero no se ha podido consultar", codigo)
        return Normativa([], {}, referencias)

    fuentes: list[Fuente] = []
    anadido = 0
    for documento in bdns.documentos(datos)[:2]:
        contenido = bdns.descargar(documento["id"])
        if not contenido:
            continue
        texto, paginas, _ = texto_con_paginas(contenido)
        if len(texto) < 500:  # un PDF escaneado sin texto no aporta nada
            continue
        if anadido + len(texto) > LIMITE_ANADIDO:
            texto = texto[: max(0, LIMITE_ANADIDO - anadido)]
            if len(texto) < 500:
                break
        anadido += len(texto)
        fuentes.append(Fuente(
            titulo=f"{documento.get('descripcion') or 'Documento de la convocatoria'} "
                   f"(BDNS {codigo})",
            texto=texto,
            url=bdns.URL_PUBLICA.format(codigo=codigo),
            paginas=paginas))

    registro.info("BDNS %s: %d documento(s) anadidos al resumen", codigo, len(fuentes))
    return Normativa(fuentes, datos, referencias)


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
