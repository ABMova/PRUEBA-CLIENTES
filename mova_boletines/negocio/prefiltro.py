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

La excepcion es RUIDO_SIEMPRE: tramites que nombran ayudas todos los dias
("Notificacion ... de resolucion de ayudas", "mesa de contratacion") pero que
nunca son una convocatoria a la que se pueda optar. Ahi estan tambien los
premios que convocan las universidades, que el usuario no quiere recibir.

Al margen de las ayudas, hay publicaciones que interesan por lo que anuncian:
los planes estrategicos y las estrategias de las administraciones marcan por
donde iran las ayudas de los proximos anos. SENALES_INTERES evita que se
descarten aqui; de decidir si valen se encarga el modelo.
"""
from __future__ import annotations

from negocio.extraccion import normalizar

# Publicaciones que no son ayudas pero interesan: planes y estrategias.
SENALES_INTERES = (
    "plan estrategico", "pla estrategic", "planes estrategicos", "plans estrategics",
    "estrategia", "estrategies", "estrategia valenciana", "plan director", "pla director",
    "hoja de ruta", "full de ruta", "plan de accion", "pla d'accio",
)

# Universidades: sus premios no interesan (los pidio quitar el usuario). Quien
# convoca manda: una consejeria "de Educacion, Ciencia y Universidades" NO es una
# universidad, y sus premios a la innovacion si interesan.
UNIVERSIDAD = (
    "universidad", "universitat", "universidade", "university", "rectorado", "rectorat",
    "vicerrectorado", "vicerectorat", "facultad", "facultat", "campus",
    "escuela universitaria", "escola universitaria",
)
# Cuando no consta el organismo hay que mirar el titulo, y ahi "universidades"
# aparece en el nombre de muchas consejerias: solo valen los indicios claros.
UNIVERSIDAD_EN_TITULO = (
    "universidad de", "universitat de", "universidade de", "universitat politecnica",
    "universidad politecnica", "de la universidad", "de la universitat", "del rectorado",
    "del rector", "de la facultad", "de la facultat", "vicerrectorado",
)
# Si convoca una administracion, no es un premio universitario aunque la palabra
# "universidades" salga en su nombre.
ADMINISTRACION = (
    "consejeria", "conselleria", "conselleria d", "ministerio", "departamento",
    "departament", "generalitat", "junta de", "diputacion", "diputacio", "ayuntamiento",
    "ajuntament", "gobierno de", "govern", "xunta", "comunidad autonoma", "instituto",
)
PREMIO = ("premio", "premios", "premi ", "premis", "certamen", "certamenes")

# Si aparece cualquiera de estas, el titulo puede ser una ayuda: no se descarta.
SENALES_AYUDA = (
    "subvencion", "subvencions", "subvencione", "ayuda", "ajut", "auxilio",
    "premio", "premis", "incentiv", "bases reguladoras", "bases regulador",
    "bdns", "concesion directa", "linea de financiacion", "prestamo", "credito fiscal",
    "convocatoria de ayudas", "convocatoria de subvenciones", "fondo perdido",
)

# Estas ganan a la regla de oro: son tramites personales o de contratacion que
# citan ayudas constantemente. Se eligen por ser inequivocas.
RUIDO_SIEMPRE: dict[str, tuple[str, ...]] = {
    "tramite sin convocatoria": (
        "notificaciones.", "notificacion de resolucion", "edicto de notificacion",
        "anuncio de notificacion", "notificacion por comparecencia",
        "al no haber podido practicar la notificacion",
    ),
    "contratacion publica": (
        "mesa de contratacion", "mesa de contractacio", "perfil del contratante",
        "perfil de contractant", "formalizacion del contrato",
    ),
    # Solo lo inequivoco: una lista de admitidos o un concurso de meritos si
    # pueden aparecer en el titulo de una convocatoria de ayudas.
    "empleo publico": ("libre designacion", "lliure designacio"),
}

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


def es_premio_de_universidad(texto: str, organismo: str = "") -> bool:
    """Premios y certamenes convocados por una universidad (no por una consejeria)."""
    if not any(palabra in texto for palabra in PREMIO):
        return False
    if organismo:
        if any(palabra in organismo for palabra in ADMINISTRACION):
            return False
        return any(palabra in organismo for palabra in UNIVERSIDAD)
    return any(palabra in texto for palabra in UNIVERSIDAD_EN_TITULO)


def motivo_ruido(titulo: str, seccion: str = "", organismo: str = "") -> str | None:
    """Familia de ruido si el titulo no es una ayuda; None si puede serlo."""
    texto = normalizar(f"{titulo} {seccion}")
    quien = normalizar(organismo)
    if not texto:
        return None
    for familia, expresiones in RUIDO_SIEMPRE.items():
        if any(expresion in texto for expresion in expresiones):
            return familia
    if es_premio_de_universidad(texto, quien):
        return "premio de universidad"
    if any(senal in texto for senal in SENALES_AYUDA):
        return None
    if any(senal in texto for senal in SENALES_INTERES):
        return None
    for familia, expresiones in RUIDO.items():
        for expresion in expresiones:
            if expresion in texto:
                return familia
    return None
