"""Fases 3, 4 y 4 bis: extraccion estructurada, relevancia y bucle de calidad.

El modelo solo interviene aqui, sobre publicaciones que ya pasaron el filtro
determinista de palabras clave.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import config
from integraciones import anthropic_cliente
from negocio.extraccion import lineas, normalizar

registro = logging.getLogger(__name__)

PENDIENTE = config.MARCADOR_PENDIENTE

SISTEMA_EXTRACCION = """Eres un analista de convocatorias publicas espanolas. Recibes el texto integro de una publicacion de un boletin oficial autonomico.

Devuelve EXCLUSIVAMENTE un objeto JSON valido, sin texto antes ni despues, con este esquema:

{
  "es_convocatoria_ayuda": true,
  "titulo": "texto literal del titulo de la publicacion",
  "resumen": "maximo 5 lineas, objeto de la ayuda y a quien se dirige",
  "organismo_convocante": "nombre completo del organismo",
  "plazo_solicitud": "fecha o periodo tal como figura, o [PENDIENTE: dato]",
  "beneficiarios": "descripcion de los beneficiarios potenciales, o [PENDIENTE: dato]",
  "importe": "importe o presupuesto con su unidad, o [PENDIENTE: dato]",
  "confianza": "alta|media|baja",
  "motivo_confianza": "una frase"
}

Reglas:
- No inventes ningun dato. Si un dato no aparece en el texto, escribe exactamente [PENDIENTE: dato]. Nunca escribas "no disponible", "no consta", "no especificado" ni ningun equivalente: el unico marcador admitido es [PENDIENTE: dato].
- "es_convocatoria_ayuda" es false cuando la publicacion solo menciona las palabras clave de pasada: nombramientos, contratacion administrativa, anuncios de licitacion, correcciones de errores sin contenido nuevo.
- El resumen no supera 5 lineas ni incluye valoraciones propias.
- El titulo se copia literal de la publicacion."""

SISTEMA_RELEVANCIA = """Clasificas convocatorias de ayudas publicas segun su interes para una empresa industrial o pyme.

Devuelve solo JSON: {"relevancia": "alta|media|baja", "sectores": ["..."], "justificacion": "una o dos frases"}

Asigna alta cuando los beneficiarios son expresamente empresas, pymes, autonomos o industria, o cuando el objeto es inversion productiva, modernizacion industrial, innovacion, digitalizacion, sostenibilidad o eficiencia energetica en el ambito empresarial.
Asigna baja cuando se dirige a particulares, entidades locales, asociaciones sin animo de lucro o al ambito academico sin vertiente empresarial.
No justifiques mas de dos frases."""

_CAMPOS = ("es_convocatoria_ayuda", "titulo", "resumen", "organismo_convocante",
           "plazo_solicitud", "beneficiarios", "importe", "confianza", "motivo_confianza")

_GENERICOS = ("no disponible", "no consta", "no especificado", "no procede", "sin datos",
              "no indicado", "desconocido", "n/a", "na", "-", "pendiente")


@dataclass
class ResultadoExtraccion:
    datos: dict
    revision_manual: bool = False
    motivo: str = ""
    llamadas: int = 0
    avisos: list[str] = field(default_factory=list)


def validar(datos: dict) -> list[str]:
    """Bucle de calidad: comprobaciones deterministas sobre la respuesta."""
    problemas: list[str] = []
    if not isinstance(datos, dict):
        return ["La respuesta no es un objeto JSON"]

    for campo in _CAMPOS:
        if campo not in datos:
            problemas.append(f"Falta el campo {campo}")

    titulo = str(datos.get("titulo", "")).strip()
    if not titulo:
        problemas.append("El titulo esta vacio")

    resumen = str(datos.get("resumen", "")).strip()
    if not resumen:
        problemas.append("El resumen esta vacio")
    elif lineas(resumen) > 5:
        problemas.append("El resumen supera las 5 lineas")

    for campo in ("plazo_solicitud", "beneficiarios", "importe", "organismo_convocante"):
        valor = str(datos.get(campo, "")).strip()
        if normalizar(valor) in _GENERICOS:
            problemas.append(
                f"El campo {campo} usa un texto generico en vez de {PENDIENTE}")

    confianza = normalizar(str(datos.get("confianza", "")))
    if confianza and confianza not in ("alta", "media", "baja"):
        problemas.append("El campo confianza no es alta, media ni baja")

    return problemas


def _mensaje_extraccion(publicacion: dict) -> str:
    return (
        f"BOLETIN: {publicacion.get('boletin_nombre', '')} ({publicacion.get('codigo_boletin', '')})\n"
        f"COMUNIDAD: {publicacion.get('comunidad', '')}\n"
        f"FECHA DE PUBLICACION: {publicacion.get('fecha_publicacion', '')}\n"
        f"SECCION: {publicacion.get('seccion', '')}\n"
        f"ORGANISMO SEGUN EL SUMARIO: {publicacion.get('organismo', '')}\n"
        f"TITULO SEGUN EL SUMARIO: {publicacion.get('titulo', '')}\n\n"
        f"TEXTO DE LA PUBLICACION:\n{publicacion.get('texto', '')}"
    )


def extraer(publicacion: dict, modelo: str, max_tokens: int, llamar=None) -> ResultadoExtraccion:
    """Fase 3 + fase 4 bis. Nunca descarta por un fallo del validador."""
    llamar = llamar or anthropic_cliente.llamar_json
    mensaje = _mensaje_extraccion(publicacion)
    llamadas = 0

    try:
        datos = llamar(SISTEMA_EXTRACCION, mensaje, modelo, max_tokens)
        llamadas += 1
    except anthropic_cliente.ErrorModelo as error:
        return ResultadoExtraccion(
            datos=_esqueleto(publicacion), revision_manual=True,
            motivo=f"La extraccion fallo: {error}", llamadas=llamadas)

    problemas = validar(datos)
    if problemas:
        # Un unico reintento, con el error concreto anadido al prompt.
        aviso = ("La respuesta anterior tenia estos problemas y debes corregirlos: "
                 + "; ".join(problemas))
        try:
            datos_segundo = llamar(SISTEMA_EXTRACCION + "\n\n" + aviso, mensaje, modelo, max_tokens)
            llamadas += 1
            problemas_segundo = validar(datos_segundo)
            if not problemas_segundo:
                return ResultadoExtraccion(datos=_completar(datos_segundo, publicacion),
                                           llamadas=llamadas)
            datos = datos_segundo
            problemas = problemas_segundo
        except anthropic_cliente.ErrorModelo as error:
            problemas.append(f"El reintento fallo: {error}")

        return ResultadoExtraccion(
            datos=_completar(datos if isinstance(datos, dict) else _esqueleto(publicacion),
                             publicacion),
            revision_manual=True, motivo="; ".join(problemas)[:500], llamadas=llamadas)

    return ResultadoExtraccion(datos=_completar(datos, publicacion), llamadas=llamadas)


def _esqueleto(publicacion: dict) -> dict:
    return {
        "es_convocatoria_ayuda": True,
        "titulo": publicacion.get("titulo", ""),
        "resumen": PENDIENTE,
        "organismo_convocante": publicacion.get("organismo", "") or PENDIENTE,
        "plazo_solicitud": PENDIENTE,
        "beneficiarios": PENDIENTE,
        "importe": PENDIENTE,
        "confianza": "baja",
        "motivo_confianza": "No se pudo analizar el texto con el modelo",
    }


def _completar(datos: dict, publicacion: dict) -> dict:
    """Rellena huecos con el marcador, nunca con valores plausibles."""
    completo = dict(datos)
    completo.setdefault("es_convocatoria_ayuda", True)
    if not str(completo.get("titulo", "")).strip():
        completo["titulo"] = publicacion.get("titulo", "")
    for campo in ("resumen", "organismo_convocante", "plazo_solicitud", "beneficiarios", "importe"):
        valor = str(completo.get(campo, "")).strip()
        if not valor or normalizar(valor) in _GENERICOS:
            completo[campo] = PENDIENTE
    completo.setdefault("confianza", "media")
    completo.setdefault("motivo_confianza", PENDIENTE)
    return completo


# ------------------------------------------------------------------ fase 4 --
def clasificar(publicacion: dict, datos: dict, modelo: str, max_tokens: int,
               terminos_refuerzo: list[str], llamar=None) -> dict:
    """Relevancia del modelo, reforzada por la lista de terminos configurable."""
    llamar = llamar or anthropic_cliente.llamar_json
    mensaje = (
        f"TITULO: {datos.get('titulo', '')}\n"
        f"ORGANISMO: {datos.get('organismo_convocante', '')}\n"
        f"BENEFICIARIOS: {datos.get('beneficiarios', '')}\n"
        f"IMPORTE: {datos.get('importe', '')}\n"
        f"RESUMEN: {datos.get('resumen', '')}\n"
        f"COMUNIDAD: {publicacion.get('comunidad', '')}"
    )

    resultado = {"relevancia": "media", "sectores": [], "justificacion": PENDIENTE,
                 "llamadas": 0, "refuerzo": False}
    try:
        respuesta = llamar(SISTEMA_RELEVANCIA, mensaje, modelo, max_tokens)
        resultado["llamadas"] = 1
        relevancia = normalizar(str(respuesta.get("relevancia", "")))
        if relevancia in ("alta", "media", "baja"):
            resultado["relevancia"] = relevancia
        sectores = respuesta.get("sectores") or []
        if isinstance(sectores, list):
            resultado["sectores"] = [str(sector).strip() for sector in sectores if str(sector).strip()]
        justificacion = str(respuesta.get("justificacion", "")).strip()
        resultado["justificacion"] = justificacion or PENDIENTE
    except anthropic_cliente.ErrorModelo as error:
        resultado["justificacion"] = f"No se pudo clasificar con el modelo: {error}"

    if resultado["relevancia"] == "media" and _tiene_refuerzo(datos, terminos_refuerzo):
        resultado["relevancia"] = "alta"
        resultado["refuerzo"] = True
        resultado["justificacion"] += " (marcada como alta por terminos de refuerzo)"

    return resultado


def _tiene_refuerzo(datos: dict, terminos: list[str]) -> bool:
    texto = normalizar(" ".join([
        str(datos.get("titulo", "")), str(datos.get("beneficiarios", "")),
        str(datos.get("resumen", "")),
    ]))
    return any(normalizar(termino) in texto for termino in terminos if termino.strip())


def json_crudo(datos: dict, clasificacion: dict) -> str:
    return json.dumps({"extraccion": datos, "relevancia": clasificacion}, ensure_ascii=False)
