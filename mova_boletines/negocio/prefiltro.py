"""Descarte previo, sin IA, de lo que nunca es una ayuda.

Un boletin publica muchas mas cosas que convocatorias: puestos de trabajo,
procesos selectivos, licitaciones, notificaciones, expropiaciones. Casi todas
llevan la palabra "convocatoria" o "resolucion", asi que pasan el filtro de
palabras clave y se pagaba al modelo por leerlas una a una.

Este modulo las aparta antes de llamar a la IA. Es deterministe y gratis.

REGLA DE ORO: si el titulo nombra una ayuda (subvencion, ayuda, premio,
incentivo, bases reguladoras, BDNS...), NO se descarta aqui aunque tambien
hable de puestos o contratos. En la duda decide el modelo, como hasta ahora:
perder una convocatoria cuesta mucho mas que analizar una de mas.
"""
from __future__ import annotations

from negocio.extraccion import normalizar

# Si aparece cualquiera de estas, el titulo puede ser una ayuda: no se descarta.
SENALES_AYUDA = (
    "subvencion", "subvencions", "subvencione", "ayuda", "ajut", "auxilio",
    "premio", "premis", "incentiv", "bases reguladoras", "bases regulador",
    "bdns", "concesion directa", "linea de financiacion", "prestamo", "credito fiscal",
    "convocatoria de ayudas", "convocatoria de subvenciones", "fondo perdido",
)

# Lo que nunca es una ayuda, por familias (castellano, catalan y valenciano).
RUIDO: dict[str, tuple[str, ...]] = {
    "empleo publico": (
        "libre designacion", "lliure designacio", "proceso selectivo", "procesos selectivos",
        "proces selectiu", "processos selectius", "concurso de meritos", "concurso especifico",
        "concurs de merits", "concurs especific", "concurso de traslados", "concurs de trasllats",
        "provision de puestos", "provision, por el sistema", "provisio, pel sistema",
        "provisio de llocs", "para cubrir, mediante el sistema", "para cubrir puesto",
        "para cubrir el puesto", "para cubrir una plaza", "para cubrir plazas",
        "oferta de empleo publico", "ofertas de empleo", "oferta publica de empleo",
        "bolsa de empleo", "bolsa de trabajo", "bolsas de trabajo", "borsa de treball",
        "lista de admitidos", "listas de admitidos", "relacion de aspirantes",
        "aspirantes admitidos", "admitidos y excluidos", "admesos i exclosos",
        "tribunal calificador", "personas que han superado", "han superado las pruebas",
        "nombramiento", "nombramientos", "nomenament", "toma de posesion",
        "plaza de profesor", "plazas de profesor", "plaza de personal", "plazas de personal",
        "personal funcionario", "funcionario de carrera", "funcionarios de carrera",
        "concurso-oposicion", "oposiciones",
    ),
    "contratacion publica": (
        "mesa de contratacion", "mesa de contractacio", "perfil del contratante",
        "perfil de contractant", "licitacion", "licitacio", "pliego de clausulas",
        "plec de clausules", "adjudicacion del contrato", "formalizacion del contrato",
        "formalitzacio del contracte", "contrato de servicios", "contrato de obras",
        "contrato de suministro", "encargo a medio propio",
    ),
    "tramite sin convocatoria": (
        "informacion publica", "informacio publica", "tramite de audiencia",
        "tramit d'audiencia", "declaracion de impacto ambiental", "impacto ambiental",
        "impacte ambiental", "autorizacion ambiental", "autoritzacio ambiental",
        "expropiacion", "expropiacio", "emplazamiento", "citacion para", "requerimiento",
        "deslinde", "amojonamiento", "notificacion de resolucion", "notificaciones.",
        "edicto de notificacion", "anuncio de notificacion", "acuerdo de inicio",
        "informe de fiscalizacion", "cuenta general", "presupuesto general",
        "aprobacion definitiva del presupuesto", "ordenanza fiscal", "padron fiscal",
        "convenio colectivo", "conveni colectiu", "tablas salariales",
    ),
}


def motivo_ruido(titulo: str, seccion: str = "") -> str | None:
    """Familia de ruido si el titulo no es una ayuda; None si puede serlo."""
    texto = normalizar(f"{titulo} {seccion}")
    if not texto:
        return None
    if any(senal in texto for senal in SENALES_AYUDA):
        return None
    for familia, expresiones in RUIDO.items():
        for expresion in expresiones:
            if expresion in texto:
                return familia
    return None
