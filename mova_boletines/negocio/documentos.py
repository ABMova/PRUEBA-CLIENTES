"""Resumen corto, resumen ampliado e infografia de una publicacion.

Mismo enfoque que la aplicacion Resumen Ayudas (MOVA):
  1. Se descarga el PDF oficial y se extrae su texto integro con marcas
     [Pagina N], para que la IA pueda citar de donde sale cada dato.
  2. La IA extrae UNA vez un JSON con todos los datos de la convocatoria
     (mismas instrucciones que Resumen Ayudas).
  3. Tres plantillas con el membrete MOVA convierten ese JSON en los tres
     documentos. Generarlos no vuelve a llamar a la IA: el JSON se guarda.

Se generan bajo demanda (al pulsar el boton), no en la vigilancia diaria:
leer el PDF entero cuesta bastante mas que el analisis del sumario.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import threading
import unicodedata
from datetime import datetime
from functools import lru_cache

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from datos import repositorio
from integraciones import anthropic_cliente
from negocio.boletines.base import ErrorBoletin, pedir
from negocio import pdf
from negocio.extraccion import texto_con_paginas

registro = logging.getLogger(__name__)

TIPOS = {
    "corto": ("Resumen corto", "5 apartados"),
    "ampliado": ("Resumen ampliado", "11 apartados"),
    "infografia": ("Infografia", "Datos clave"),
}

# Unos 150.000 tokens: cabe de sobra en Sonnet 5 y Opus 5 (1M de contexto) y
# acota el coste de unas bases reguladoras muy largas. Si se supera, se avisa
# en el propio documento: nunca se recorta en silencio.
LIMITE_CARACTERES = 600_000
MINIMO_CARACTERES = 200
NO_DISPONIBLE = "Se establece en la correspondiente convocatoria."


class ErrorDocumento(Exception):
    """No se ha podido preparar el documento; el mensaje es para el usuario."""


# --------------------------------------------- instrucciones (Resumen Ayudas) --
SISTEMA_EXTRACCION = (
    "Eres un experto en análisis jurídico-administrativo de subvenciones públicas españolas. "
    "Analizas textos de boletines oficiales (BOE, DOGV, BORM, BOJA, BOA, BOCM, etc.) con precisión, "
    "rigor jurídico y EXHAUSTIVIDAD. Tu objetivo es no dejar ningún campo sin rellenar siempre que el "
    "dato exista en el texto. No inventes datos inexistentes, pero extrae todo lo presente aunque esté "
    "disperso. Recuerda: el régimen de minimis tiene un límite de 300.000 € por beneficiario en tres "
    "años; las intensidades en porcentaje se expresan con el símbolo %; el plazo de ejecución se "
    "redacta \"desde la fecha de inicio hasta la fecha final\". Responde SOLO con JSON puro, sin markdown."
)

PROMPT_EXTRACCION = """Analiza EXHAUSTIVAMENTE el texto de uno o varios documentos oficiales de subvención pública española y extrae TODOS los datos. Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni markdown.

REGLAS DE EXTRACCIÓN OBLIGATORIAS:
1. EXHAUSTIVIDAD: rellena TODOS los campos. Lee el texto completo, incluidos articulado y anexos, y no dejes ningún campo vacío si la información aparece explícita o puede deducirse con claridad del contenido. Usa null SOLO cuando el dato realmente no exista en el texto. Esfuérzate especialmente en completar: beneficiarios, actuaciones, gastos elegibles, cuantía, intensidad, criterios de valoración, documentación de solicitud y de justificación, y todos los plazos.
2. RÉGIMEN DE MINIMIS: si el texto menciona "minimis" o "de minimis", indica SIEMPRE, en el campo "regimen" y en "compatibilidades", que el límite es de 300.000 € por beneficiario en un periodo de tres años.
3. INTENSIDAD: la intensidad de la ayuda debe expresarse SIEMPRE en formato porcentaje con el símbolo % (por ejemplo "70%", nunca "70" ni "70 por ciento"). Si en el texto figura como fracción o proporción (por ejemplo 0,7), conviértela a porcentaje (70%).
4. PLAZO DE EJECUCIÓN: el campo "plazo_ejecucion" debe redactarse como "desde [fecha de inicio] hasta [fecha final]" cuando existan ambas fechas. Si solo hay una, indícala con claridad.
5. IMPORTES: todos los importes económicos (cuantías, crédito, inversión) deben expresarse con separador de miles y el símbolo del euro (por ejemplo "12.000 €", "1.500.000 €").
6. FECHAS: todas las fechas en formato dd/mm/aaaa (por ejemplo "30/09/2024").
7. PLAZOS DE PRESENTACIÓN: en "plazo_inicio" y "plazo_fin" indica solo la fecha en formato dd/mm/aaaa, SIN la hora.
8. No inventes datos que no estén en el texto, pero sé minucioso: extrae cada dato presente aunque esté disperso en distintos artículos o anexos.
9. ACTUACIONES vs COSTES (distínguelos, NO los mezcles): "actuaciones" = las ACCIONES, proyectos o actividades subvencionables (QUÉ se puede hacer: p. ej. "digitalización del comercio minorista", "reforma del local"). "gastos_elegibles" = los COSTES o GASTOS subvencionables (QUÉ gastos se pueden financiar: p. ej. "licencias de software", "equipos informáticos", "obra civil"). Una actividad va SIEMPRE en "actuaciones"; un gasto o coste va SIEMPRE en "gastos_elegibles". Rellena AMBOS campos de forma diferenciada y completa; no dupliques el mismo contenido en los dos.
10. EJECUCIÓN Y PAGO: en "ejecucion_pago" indica el PERIODO en el que las actuaciones subvencionadas deben estar REALIZADAS Y PAGADAS según la orden o la convocatoria (por ejemplo "entre el 01/01/2026 y el 31/12/2026" o "desde la resolución hasta el 30/09/2026"). Si el texto no lo especifica, usa null.
11. FUENTES: en "fuentes" indica, para cada campo que hayas rellenado, de dónde sale el dato con el formato "Art. 5.2, pág. 3" (usa las marcas [Página N] del texto y la numeración de artículos, bases o anexos; si el dato aparece en varios sitios, cítalos separados por "; "). Si no puedes localizarlo con seguridad, escribe "sin localizar". No incluyas en "fuentes" los campos que queden a null.

Estructura JSON requerida:
{"nombre_ayuda":null,"organismo":null,"linea":null,"ambito":null,"regimen":null,"claim":null,"objeto":null,
"beneficiarios":null,"exclusiones":null,"benef_corto":null,
"actuaciones":[],"gastos_elegibles":[],"gastos_excluidos":[],
"cuantia_max":null,"cuantia_min":null,"intensidad":null,"inversion_min":null,"inversion_max":null,
"credito":null,"criterios":[],"doc_solicitud":[],"doc_justificacion":[],
"plazo_inicio":null,"plazo_fin":null,"plazo_ejecucion":null,"plazo_justificacion":null,"ejecucion_pago":null,
"compatibilidades":null,"incompatibilidades":null,
"referencias":[],"enlaces":[],"cierre":null,"alertas":[],
"fuentes":{"nombre_del_campo":"Art. X, pág. N"}}

PUBLICACIÓN (datos del sumario del boletín):
{PUBLICACION}

El texto íntegro de la publicación está en las instrucciones de sistema, bajo "DOCUMENTACIÓN OFICIAL APORTADA"."""


# ------------------------------------------------------------ texto del PDF --
def _descargar(url: str, codigo_boletin: str):
    es_borm = codigo_boletin == "BORM"
    return pedir(url, navegador=es_borm, tls_legado=(codigo_boletin == "DOGC"),
                 cabeceras={"Referer": "https://www.borm.es/"} if es_borm else None)


def texto_de_publicacion(publicacion: dict) -> tuple[str, str, int, bool]:
    """Devuelve (texto, fuente, paginas, incompleto).

    Primero el PDF oficial; si no hay o no tiene texto, la pagina HTML oficial.
    """
    codigo = publicacion.get("codigo_boletin", "")
    url_pdf = publicacion.get("url_pdf") or ""
    if url_pdf:
        try:
            respuesta = _descargar(url_pdf, codigo)
            if respuesta.content[:5] == b"%PDF-":
                texto, paginas, incompleto = texto_con_paginas(respuesta.content)
                if len(texto) >= MINIMO_CARACTERES:
                    return texto, url_pdf, paginas, incompleto
        except ErrorBoletin as error:
            registro.warning("No se pudo descargar el PDF %s: %s", url_pdf, error)

    url_html = publicacion.get("url_oficial") or ""
    if url_html and "#/" not in url_html:  # las rutas con # son aplicaciones de pagina unica
        try:
            respuesta = _descargar(url_html, codigo)
            sopa = BeautifulSoup(respuesta.text, "html.parser")
            for sobrante in sopa(["script", "style", "nav", "header", "footer"]):
                sobrante.decompose()
            texto = re.sub(r"\n{3,}", "\n\n", sopa.get_text("\n", strip=True))
            if len(texto) >= MINIMO_CARACTERES:
                return f"[Página 1]\n{texto}", url_html, 1, False
        except ErrorBoletin as error:
            registro.warning("No se pudo descargar la pagina %s: %s", url_html, error)

    raise ErrorDocumento(
        "No se ha podido leer el texto de la publicacion: el PDF oficial no se ha podido "
        "descargar o no contiene texto. Abre el enlace oficial y comprueba que esta disponible.")


# ------------------------------------------------------------- extraccion IA --
def _ficha(publicacion: dict) -> str:
    return (f"Boletín: {publicacion.get('boletin_nombre', '')} ({publicacion.get('codigo_boletin', '')})\n"
            f"Comunidad: {publicacion.get('comunidad', '')}\n"
            f"Fecha de publicación: {publicacion.get('fecha_publicacion', '')}\n"
            f"Título: {publicacion.get('titulo', '')}\n"
            f"Organismo: {publicacion.get('organismo', '')}\n"
            f"Enlace oficial: {publicacion.get('url_oficial', '')}\n"
            f"PDF: {publicacion.get('url_pdf', '')}")


def extraer_datos(publicacion: dict, llamar=None) -> tuple[dict, dict]:
    """Devuelve (datos, metadatos). llamar se sustituye en las pruebas."""
    llamar = llamar or anthropic_cliente.llamar_json
    texto, fuente, paginas, incompleto = texto_de_publicacion(publicacion)

    recortado = len(texto) > LIMITE_CARACTERES
    if recortado:
        texto = texto[:LIMITE_CARACTERES] + "\n[...texto recortado por longitud máxima...]"

    sistema = (SISTEMA_EXTRACCION + "\n\nDOCUMENTACIÓN OFICIAL APORTADA (texto íntegro con marcas "
               "[Página N]):\n\n" + texto)
    mensaje = PROMPT_EXTRACCION.replace("{PUBLICACION}", _ficha(publicacion))
    modelo = repositorio.ajuste("modelo_documentos", "claude-sonnet-5")
    max_tokens = repositorio.ajuste_int("max_tokens_documentos", 16000)

    datos = None
    ultimo_error: Exception | None = None
    for intento in range(2):  # como Resumen Ayudas: un reintento si el JSON no es valido
        try:
            datos = llamar(sistema, mensaje, modelo, max_tokens,
                           fase="documentos" if intento == 0 else "documentos_reintento")
            if isinstance(datos, dict):
                break
            datos = None
        except anthropic_cliente.TopeAlcanzado:
            raise
        except anthropic_cliente.ErrorModelo as error:
            ultimo_error = error
            if "JSON" not in str(error):
                raise
    if datos is None:
        raise anthropic_cliente.ErrorModelo(
            f"La respuesta de la IA no es un JSON valido tras dos intentos ({ultimo_error}).")

    # Enlaces oficiales siempre presentes, aunque la IA no los haya citado.
    enlaces = [e for e in (datos.get("enlaces") or []) if isinstance(e, str)]
    for enlace in (publicacion.get("url_oficial"), publicacion.get("url_pdf")):
        if enlace and enlace.startswith("http") and "#/" not in enlace and enlace not in enlaces:
            enlaces.append(enlace)
    datos["enlaces"] = enlaces

    alertas = list(datos.get("alertas") or [])
    if recortado:
        alertas.append(f"La publicación es muy extensa: solo se han analizado los primeros "
                       f"{LIMITE_CARACTERES:,} caracteres.".replace(",", "."))
    if incompleto:
        alertas.append("Parte del PDF no tenía texto legible (páginas escaneadas sin OCR): "
                       "revisa el documento original.")
    datos["alertas"] = alertas

    return datos, {"modelo": modelo, "fuente": fuente, "paginas": paginas,
                   "caracteres": len(texto), "recortado": recortado}


# ------------------------------------------------------- generacion en fondo --
_en_curso: set[int] = set()
_lock = threading.Lock()


def generando(publicacion_id: int) -> bool:
    with _lock:
        return publicacion_id in _en_curso


def lanzar(publicacion_id: int, usuario: str) -> tuple[bool, str]:
    """Arranca la extraccion en un hilo. (aceptada, mensaje)."""
    if not anthropic_cliente.hay_clave():
        return False, "No hay clave de API de Anthropic: configurala en Ajustes."
    queda, gasto, tope = anthropic_cliente.presupuesto()
    if not queda:
        return False, (f"Tope de gasto mensual alcanzado ({gasto:.2f} de {tope:.2f} $). "
                       f"Subelo en Ajustes para generar documentos.")
    with _lock:
        if publicacion_id in _en_curso:
            return True, "Ya se esta generando"
        _en_curso.add(publicacion_id)
    repositorio.marcar_documento(publicacion_id, "generando", usuario)
    hilo = threading.Thread(target=_generar, args=(publicacion_id, usuario),
                            name=f"documento-{publicacion_id}", daemon=True)
    hilo.start()
    return True, "Generacion iniciada"


def _generar(publicacion_id: int, usuario: str) -> None:
    try:
        fila = repositorio.publicacion(publicacion_id)
        if fila is None:
            raise ErrorDocumento("La publicacion ya no existe.")
        datos, meta = extraer_datos(dict(fila))
        repositorio.guardar_documento(publicacion_id, json.dumps(datos, ensure_ascii=False),
                                      meta["modelo"], meta["fuente"], meta["paginas"],
                                      meta["caracteres"], meta["recortado"])
        repositorio.registrar_auditoria(usuario, "generar_documentos", str(publicacion_id),
                                        f"{meta['paginas']} pag., modelo {meta['modelo']}")
    except (ErrorDocumento, anthropic_cliente.ErrorModelo) as error:
        repositorio.marcar_documento(publicacion_id, "error", error=str(error))
        repositorio.registrar_auditoria(usuario, "generar_documentos", str(publicacion_id),
                                        str(error), resultado="error")
    except Exception as error:  # noqa: BLE001 - nunca debe tumbar el servidor
        registro.exception("Fallo generando documentos de %s", publicacion_id)
        repositorio.marcar_documento(publicacion_id, "error",
                                     error=f"Error inesperado: {type(error).__name__}: {error}")
    finally:
        with _lock:
            _en_curso.discard(publicacion_id)
        repositorio.cerrar_conexion()


# ---------------------------------------------------------------- plantillas --
@lru_cache(maxsize=None)
def _imagen(nombre: str) -> str:
    ruta = config.RUTA_ESTATICOS / "marca" / nombre
    return "data:image/png;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def _vacio(valor) -> bool:
    return valor is None or valor in ("", "null") or (isinstance(valor, (list, dict)) and not valor)


def item_a_texto(x) -> str:
    """Cualquier elemento de lista (texto u objeto) a texto legible (como Resumen Ayudas)."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, (int, float, bool)):
        return str(x)
    if isinstance(x, list):
        return "; ".join(t for t in (item_a_texto(i) for i in x) if t)
    if isinstance(x, dict):
        for clave in ("actuacion", "actuación", "nombre", "titulo", "título", "concepto", "gasto",
                      "coste", "item", "texto", "valor"):
            if str(x.get(clave) or "").strip():
                base = str(x[clave]).strip()
                detalle = str(x.get("descripcion") or x.get("descripción") or x.get("detalle") or "").strip()
                return f"{base}: {detalle}" if detalle and detalle != base else base
        return " — ".join(str(v).strip() for v in x.values()
                          if v is not None and not isinstance(v, (dict, list)) and str(v).strip())
    return str(x)


def fecha_larga(texto) -> str:
    t = str(texto or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", t)
    if not m:
        return t
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    mes = int(m.group(2))
    return f"{int(m.group(1))} de {meses[mes - 1]} de {m.group(3)}" if 1 <= mes <= 12 else t


def _contexto(datos: dict, publicacion: dict) -> dict:
    def v(clave: str, defecto: str = NO_DISPONIBLE) -> str:
        valor = datos.get(clave)
        return defecto if _vacio(valor) else item_a_texto(valor)

    def lista(clave: str) -> list[str]:
        valor = datos.get(clave)
        if _vacio(valor):
            return []
        if isinstance(valor, list):
            return [t for t in (item_a_texto(i) for i in valor) if t]
        return [item_a_texto(valor)]

    intensidad = None if _vacio(datos.get("intensidad")) else item_a_texto(datos["intensidad"])
    cuantia = None if _vacio(datos.get("cuantia_max")) else item_a_texto(datos["cuantia_max"])
    if intensidad and cuantia:
        tipo_cuantia = f"Hasta el {intensidad} con una cuantía máxima de {cuantia}."
    elif cuantia:
        tipo_cuantia = f"Cuantía máxima de {cuantia}."
    elif intensidad:
        tipo_cuantia = f"Hasta el {intensidad}."
    else:
        tipo_cuantia = NO_DISPONIBLE

    fin = None if _vacio(datos.get("plazo_fin")) else str(datos["plazo_fin"])
    inicio = None if _vacio(datos.get("plazo_inicio")) else str(datos["plazo_inicio"])
    plazo_txt = (f"Finaliza el {fecha_larga(fin)}." if fin
                 else f"Desde el {fecha_larga(inicio)}." if inicio else NO_DISPONIBLE)

    ejecucion = datos.get("ejecucion_pago") if not _vacio(datos.get("ejecucion_pago")) \
        else datos.get("plazo_ejecucion")
    ejecucion_frase = (f"Las actuaciones deben estar realizadas y pagadas en el periodo: "
                       f"{item_a_texto(ejecucion)}." if not _vacio(ejecucion) else
                       "El plazo en que las actuaciones deben estar realizadas y pagadas se "
                       "establece en la correspondiente convocatoria.")
    inversion_frase = (f"Requiere una inversión mínima de {item_a_texto(datos['inversion_min'])}."
                       if not _vacio(datos.get("inversion_min")) else "No se exige inversión mínima.")

    criterios = []
    for criterio in datos.get("criterios") or []:
        if isinstance(criterio, dict):
            criterios.append({"criterio": str(criterio.get("criterio") or item_a_texto(criterio)),
                              "puntos": str(criterio.get("puntos") or ""),
                              "descripcion": str(criterio.get("descripcion") or "")})
        elif item_a_texto(criterio):
            criterios.append({"criterio": item_a_texto(criterio), "puntos": "", "descripcion": ""})

    return {
        "d": datos, "v": v, "lista": lista, "pub": publicacion,
        "tipo_cuantia": tipo_cuantia, "plazo_txt": plazo_txt,
        "ejecucion_frase": ejecucion_frase, "inversion_frase": inversion_frase,
        "criterios": criterios,
        "enlaces": [e for e in lista("enlaces") if e.startswith("http")],
        "logo_oro": _imagen("logo-oro.png"), "logo_negro": _imagen("logo-negro.png"),
        "edificio": _imagen("edificio-fondo.png"),
        "no_disponible": NO_DISPONIBLE,
        "generado": datetime.now().strftime("%d/%m/%Y"),
    }


def _entorno() -> Environment:
    return Environment(loader=FileSystemLoader(str(config.RUTA_PLANTILLAS / "documentos")),
                       autoescape=select_autoescape(["html"]))


def renderizar(tipo: str, datos: dict, publicacion: dict, barra: dict | None = None,
               para_pdf: bool = False) -> str:
    """HTML autocontenido del documento. barra: botones de la aplicacion (no se imprimen).

    para_pdf: la infografia se convierte en UNA hoja alta, sin cortes de pagina.
    """
    if tipo not in TIPOS:
        raise ErrorDocumento("Tipo de documento desconocido")
    contexto = _contexto(datos, publicacion)
    contexto["barra"] = barra
    contexto["tipos"] = TIPOS
    contexto["tipo"] = tipo
    contexto["para_pdf"] = para_pdf
    return _entorno().get_template(f"{tipo}.html").render(**contexto)


def nombre_fichero(tipo: str, publicacion: dict, extension: str = "pdf") -> str:
    base = {"corto": "ResumenCorto", "ampliado": "ResumenAmpliado", "infografia": "Infografia"}[tipo]
    # "aprobación" -> "aprobacion" (sin la tilde, la letra no se pierde)
    sin_tildes = unicodedata.normalize("NFKD", publicacion.get("titulo_resumido") or "")
    sin_tildes = sin_tildes.encode("ascii", "ignore").decode("ascii")
    titulo = re.sub(r"[^A-Za-z0-9]+", "-", sin_tildes[:50]).strip("-")
    return f"{base}-{publicacion.get('codigo_boletin', '')}-{publicacion.get('id', '')}-{titulo}.{extension}"


def descarga(tipo: str, datos: dict, publicacion: dict) -> tuple[bytes, str, str]:
    """Fichero para el boton Descargar: (contenido, tipo MIME, nombre).

    Es un PDF. Si el equipo no tiene navegador con el que crearlo, se entrega
    el HTML (se abre igual en cualquier navegador) y se deja aviso en el registro.
    """
    try:
        contenido = pdf.html_a_pdf(renderizar(tipo, datos, publicacion, para_pdf=True))
        return contenido, "application/pdf", nombre_fichero(tipo, publicacion, "pdf")
    except pdf.ErrorPdf as exc:
        registro.warning("No se pudo crear el PDF (%s); se descarga en HTML", exc)
        html = renderizar(tipo, datos, publicacion).encode("utf-8")
        return html, "text/html", nombre_fichero(tipo, publicacion, "html")
