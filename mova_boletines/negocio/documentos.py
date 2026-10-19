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
from datetime import date, datetime
from functools import lru_cache

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from datos import repositorio
from integraciones import anthropic_cliente
from negocio.boletines.base import ErrorBoletin, pedir
from integraciones.bdns import plazo_de as bdns_plazo
from negocio import normativa, pdf, plazos
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
    "redacta \"desde la fecha de inicio hasta la fecha final\". Redacta siempre en castellano, aunque "
    "el documento venga en otra lengua oficial. Responde SOLO con JSON puro, sin markdown."
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
11. TIPO DE AYUDA: en "tipo_ayuda" escribe "financiacion" cuando lo que se concede sea un prestamo, credito, aval, garantia, linea de financiacion bonificada, bonificacion de intereses o participacion en capital (aunque lleve un tramo no reembolsable); "empleo" cuando lo subvencionado sea contratar personas, mantener el empleo, bonificar cuotas de la Seguridad Social, fomentar el autoempleo o formar trabajadores; y "general" en los demas casos. Si encajan las dos, elige la que sea el grueso de la ayuda.
12. CONDICIONES DE FINANCIACION: rellena el objeto "financiacion" SOLO si "tipo_ayuda" es "financiacion". Cada campo con el dato tal como figura en el texto, o null: "inicio_proyecto" (cuanto antes de la solicitud puede haber empezado el proyecto), "financiacion_max" (porcentaje financiable, distinguiendo inversion y circulante si el texto lo distingue), "intereses" (indice y diferencial, p. ej. "Euribor a un ano + un diferencial entre el 0,50 y el 0,75%"), "amortizacion" (plazo de devolucion), "carencia", "tramo_no_reembolsable" (porcentaje, cuantia maxima y regimen si lo indica), "garantias", "comision_apertura". La inversion minima y maxima van, como siempre, en "inversion_min" e "inversion_max".
13. AYUDAS DE EMPLEO: rellena el objeto "empleo" SOLO si "tipo_ayuda" es "empleo". "personas_destinatarias" describe a QUIEN hay que contratar (edad, titulacion, situacion de desempleo, inscripcion en registros), que no es lo mismo que "beneficiarios" (quien cobra la ayuda: la empresa). "requisitos_contratacion" son las condiciones que debe cumplir el contrato o la empresa (incremento de plantilla, numero maximo de contratos, limites de otras ayudas). "requisitos_trabajadores" son los que debe acreditar la persona contratada. "obligaciones_empresario" son los compromisos posteriores (mantenimiento del empleo y de la plantilla, sustituciones, devolucion si se incumple). "condiciones_contrato" son la modalidad, jornada y duracion exigidas. "cuantias" es una lista con un objeto {"colectivo","importe"} por cada importe distinto segun a quien se contrate (por ejemplo hombres, mujeres, personas con discapacidad, victimas de violencia de genero). Las exclusiones van, como siempre, en "exclusiones".
14. PLAZO DE PRESENTACION: si la documentacion dice cuando se puede solicitar, RELLENA "plazo_inicio" y "plazo_fin"; no remitas a "la correspondiente convocatoria" cuando el dato este en alguno de los documentos. Copia SIEMPRE en "plazo_frase" la frase literal del plazo tal como figura ("veinte dias habiles a contar desde el dia siguiente al de la publicacion del extracto"), aunque no puedas fechar el final: la fecha exacta la calcula despues la herramienta, que sabe contar habiles y festivos. Si dos documentos dicen cosas distintas, copia la del mas concreto.
15. IDIOMA: redacta SIEMPRE en castellano, aunque el documento original esté en catalán, valenciano, gallego o euskera. Traduce los textos que extraigas (objeto, actuaciones, gastos, requisitos, obligaciones); solo se conservan en su lengua los nombres propios de programas, organismos y normas.
16. FUENTES: en "fuentes" indica, para cada campo que hayas rellenado, de dónde sale el dato con el formato "Art. 5.2, pág. 3" (usa las marcas [Página N] del texto y la numeración de artículos, bases o anexos; si el dato aparece en varios sitios, cítalos separados por "; "). Si no puedes localizarlo con seguridad, escribe "sin localizar". No incluyas en "fuentes" los campos que queden a null.

Estructura JSON requerida:
{"nombre_ayuda":null,"organismo":null,"linea":null,"ambito":null,"regimen":null,"claim":null,"objeto":null,
"tipo_ayuda":"general",
"beneficiarios":null,"exclusiones":null,"benef_corto":null,
"actuaciones":[],"gastos_elegibles":[],"gastos_excluidos":[],
"cuantia_max":null,"cuantia_min":null,"intensidad":null,"inversion_min":null,"inversion_max":null,
"financiacion":{"inicio_proyecto":null,"financiacion_max":null,"intereses":null,"amortizacion":null,"carencia":null,"tramo_no_reembolsable":null,"garantias":null,"comision_apertura":null},
"empleo":{"personas_destinatarias":null,"requisitos_contratacion":[],"requisitos_trabajadores":[],"obligaciones_empresario":[],"condiciones_contrato":[],"cuantias":[]},
"credito":null,"criterios":[],"doc_solicitud":[],"doc_justificacion":[],
"plazo_inicio":null,"plazo_fin":null,"plazo_frase":null,"plazo_ejecucion":null,"plazo_justificacion":null,"ejecucion_pago":null,
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

    # Lo publicado suele ser un extracto: se busca la convocatoria completa y la
    # ficha oficial antes de resumir, que es donde estan el plazo y las cuantias.
    reunida = normativa.reunir(publicacion, texto)
    bloques = [f"=== DOCUMENTO 1: lo publicado en el boletín ===\n{texto}"]
    for numero, extra in enumerate(reunida.fuentes, start=2):
        bloques.append(f"=== DOCUMENTO {numero}: {extra.titulo} ({extra.paginas} págs.) ===\n"
                       f"{extra.texto}")
    documentacion = "\n\n".join(bloques)

    recortado = len(documentacion) > LIMITE_CARACTERES
    if recortado:
        documentacion = (documentacion[:LIMITE_CARACTERES]
                         + "\n[...texto recortado por longitud máxima...]")

    ficha_oficial = normativa.resumen_oficial(reunida.datos_bdns)
    sistema = (SISTEMA_EXTRACCION
               + ("\n\nFICHA OFICIAL DE LA BASE DE DATOS NACIONAL DE SUBVENCIONES (datos "
                  "verificados; si contradicen al texto, mandan estos):\n" + ficha_oficial
                  if ficha_oficial else "")
               + "\n\nDOCUMENTACIÓN OFICIAL APORTADA (texto íntegro con marcas [Página N]). "
                 "Cuando un dato aparezca en varios documentos, quédate con el más concreto:\n\n"
               + documentacion)
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

    # Queda escrito que se ha leido, y el plazo que da la BDNS, para el calculo.
    datos["fuentes_consultadas"] = ([f"Publicación en el boletín ({fuente})"]
                                    + [f"{f.titulo}: {f.url}" for f in reunida.fuentes])
    if reunida.datos_bdns:
        frase, fecha = bdns_plazo(reunida.datos_bdns)
        datos["plazo_bdns"] = {"codigo": reunida.datos_bdns.get("codigoBDNS", ""),
                               "texto_fin": frase, "fecha_fin": fecha}
    if reunida.referencias:
        datos["bases_citadas"] = reunida.referencias

    alertas = list(datos.get("alertas") or [])
    if recortado:
        alertas.append(f"La publicación es muy extensa: solo se han analizado los primeros "
                       f"{LIMITE_CARACTERES:,} caracteres.".replace(",", "."))
    if incompleto:
        alertas.append("Parte del PDF no tenía texto legible (páginas escaneadas sin OCR): "
                       "revisa el documento original.")
    datos["alertas"] = alertas

    return datos, {"modelo": modelo, "fuente": fuente,
                   "paginas": paginas + sum(f.paginas for f in reunida.fuentes),
                   "caracteres": len(documentacion), "recortado": recortado}


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


def _plazo_de_solicitud(datos: dict, publicacion: dict) -> tuple[str, str]:
    """Cuando acaba el plazo y como se ha llegado a esa fecha.

    Manda la fecha mas concreta que se tenga. Si el documento la dice, esa; si
    no, la que se calculo al analizar la publicacion a partir de la frase del
    plazo ("20 dias naturales desde el dia siguiente a la publicacion"), que es
    un calculo hecho en codigo y no por la IA. Solo cuando no hay ninguna de las
    dos se remite a la convocatoria.
    """
    fin = None if _vacio(datos.get("plazo_fin")) else str(datos["plazo_fin"])
    inicio = None if _vacio(datos.get("plazo_inicio")) else str(datos["plazo_inicio"])
    if fin:
        return f"Finaliza el {fecha_larga(fin)}.", ""

    # La BDNS es fuente oficial: si da la fecha ya hecha, manda.
    del_bdns = datos.get("plazo_bdns") or {}
    if del_bdns.get("fecha_fin"):
        dia = plazos.fecha_iso(str(del_bdns["fecha_fin"]))
        if dia:
            return (f"Finaliza el {plazos.en_letra(dia)}.",
                    f"Fecha publicada en la Base de Datos Nacional de Subvenciones "
                    f"(convocatoria {del_bdns.get('codigo', '')}).")

    # Si no, se calcula con la frase que mas precise: la convocatoria puede decir
    # "veinte dias habiles" donde la ficha de la BDNS dice solo "20 dias".
    texto_plazo = str(publicacion.get("plazo") or "")
    frase = plazos.mas_concreta([datos.get("plazo_frase"), texto_plazo,
                                 del_bdns.get("texto_fin")])
    if frase:
        calculado = plazos.fin_de_plazo(frase, str(publicacion.get("fecha_publicacion") or ""),
                                        str(publicacion.get("comunidad") or ""))
        if calculado.hay:
            return (f"Finaliza el {plazos.en_letra(date.fromisoformat(calculado.fin))}.",
                    calculado.explicacion)

    if publicacion.get("plazo_fin"):
        return f"Finaliza el {plazos.en_letra(date.fromisoformat(publicacion['plazo_fin']))}.", ""
    if inicio:
        return f"Desde el {fecha_larga(inicio)}.", ""
    if texto_plazo and "[PENDIENTE" not in texto_plazo:
        return item_a_texto(texto_plazo), ""
    return NO_DISPONIBLE, ""


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

    plazo_txt, plazo_calculo = _plazo_de_solicitud(datos, publicacion)

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
        "tipo_cuantia": tipo_cuantia, "plazo_txt": plazo_txt, "plazo_calculo": plazo_calculo,
        "ejecucion_frase": ejecucion_frase, "inversion_frase": inversion_frase,
        "criterios": criterios,
        "enlaces": [e for e in lista("enlaces") if e.startswith("http")],
        # Los resumenes y la infografia mantienen el logotipo de siempre: el
        # MOVA IA nuevo solo se usa en el correo, el panel y la pagina de espera.
        "logo_negro": _imagen("logo-negro.png"), "logo_oro": _imagen("logo-oro.png"),
        "tipo_ayuda": _tipo_ayuda(datos),
        "kpi": _kpi,
        "condiciones_financiacion": _condiciones_financiacion(datos),
        "fin": _financiacion_suelta(datos),
        "empleo": _datos_empleo(datos),
        "edificio": _imagen("edificio-fondo.png"),
        "no_disponible": NO_DISPONIBLE,
        "generado": datetime.now().strftime("%d/%m/%Y"),
    }


TIPOS_AYUDA = ("general", "financiacion", "empleo")

# Apartado "Condiciones de financiacion" del resumen: rotulo y de donde sale.
_CONDICIONES = (
    ("Inversión mínima", "inversion_min", False),
    ("Inversión máxima", "inversion_max", False),
    ("Inicio del proyecto", "inicio_proyecto", True),
    ("Financiación máxima", "financiacion_max", True),
    ("Intereses", "intereses", True),
    ("Amortización", "amortizacion", True),
    ("Carencia", "carencia", True),
    ("Tramo no reembolsable (TNR)", "tramo_no_reembolsable", True),
    ("Garantías", "garantias", True),
    ("Comisión de apertura", "comision_apertura", True),
)


def _kpi(valor: str) -> str:
    """Cifra destacada de la infografia: la frase larga del dato que falta no
    cabe en la caja, asi que se resume. El texto completo sigue en su apartado."""
    return "Sin especificar" if not valor or valor == NO_DISPONIBLE else valor


def _tipo_ayuda(datos: dict) -> str:
    """financiacion | empleo | general. Lo desconocido se trata como general."""
    valor = str(datos.get("tipo_ayuda") or "").strip().lower()
    return valor if valor in TIPOS_AYUDA else "general"


def _condiciones_financiacion(datos: dict) -> list[dict]:
    """Rotulo y valor de cada condicion; las que no figuren llevan el aviso de siempre."""
    bloque = datos.get("financiacion")
    bloque = bloque if isinstance(bloque, dict) else {}
    condiciones = []
    for rotulo, clave, es_del_bloque in _CONDICIONES:
        valor = bloque.get(clave) if es_del_bloque else datos.get(clave)
        condiciones.append({"rotulo": rotulo,
                            "valor": NO_DISPONIBLE if _vacio(valor) else item_a_texto(valor)})
    return condiciones


def _financiacion_suelta(datos: dict) -> dict:
    """Condiciones de financiacion una a una, para la infografia."""
    bloque = datos.get("financiacion")
    bloque = bloque if isinstance(bloque, dict) else {}
    campos = ("inicio_proyecto", "financiacion_max", "intereses", "amortizacion", "carencia",
              "tramo_no_reembolsable", "garantias", "comision_apertura")
    return {campo: (NO_DISPONIBLE if _vacio(bloque.get(campo)) else item_a_texto(bloque[campo]))
            for campo in campos}


def _cuantia_destacada(cuantias: list[dict]) -> str:
    """La cifra grande de la infografia: el importe, o el rango si hay varios."""
    importes = [c["importe"] for c in cuantias if c.get("importe") and c["importe"] != NO_DISPONIBLE]
    if not importes:
        return NO_DISPONIBLE
    if len(importes) == 1:
        return importes[0]
    def numero(texto: str) -> float:
        digitos = re.sub(r"[^0-9,.]", "", texto).replace(".", "").replace(",", ".")
        try:
            return float(digitos)
        except ValueError:
            return 0.0
    ordenados = sorted(importes, key=numero)
    menor, mayor = ordenados[0], ordenados[-1]
    return menor if menor == mayor else f"{menor} – {mayor}"


def _datos_empleo(datos: dict) -> dict:
    """Apartados propios de las ayudas de empleo, ya listos para la plantilla."""
    bloque = datos.get("empleo")
    bloque = bloque if isinstance(bloque, dict) else {}

    def lista_de(clave: str) -> list[str]:
        valor = bloque.get(clave)
        if _vacio(valor):
            return []
        if isinstance(valor, list):
            return [t for t in (item_a_texto(v) for v in valor) if t]
        return [item_a_texto(valor)]

    cuantias = []
    for cuantia in (bloque.get("cuantias") or []):
        if isinstance(cuantia, dict):
            colectivo = item_a_texto(cuantia.get("colectivo", ""))
            importe = item_a_texto(cuantia.get("importe", ""))
            if colectivo or importe:
                cuantias.append({"colectivo": colectivo, "importe": importe or NO_DISPONIBLE})
        elif not _vacio(cuantia):
            cuantias.append({"colectivo": "", "importe": item_a_texto(cuantia)})

    personas = bloque.get("personas_destinatarias")
    return {
        "personas_destinatarias": NO_DISPONIBLE if _vacio(personas) else item_a_texto(personas),
        "requisitos_contratacion": lista_de("requisitos_contratacion"),
        "requisitos_trabajadores": lista_de("requisitos_trabajadores"),
        "obligaciones_empresario": lista_de("obligaciones_empresario"),
        "condiciones_contrato": lista_de("condiciones_contrato"),
        "cuantias": cuantias,
        "cuantia_destacada": _cuantia_destacada(cuantias),
        "contrato_destacado": (lista_de("condiciones_contrato") or [NO_DISPONIBLE])[0],
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
    # Sin titulo resumido (publicaciones antiguas o sin analizar) se usa el completo.
    titulo = publicacion.get("titulo_resumido") or publicacion.get("titulo") or ""
    # "aprobación" -> "aprobacion" (sin la tilde, la letra no se pierde)
    sin_tildes = unicodedata.normalize("NFKD", titulo)
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
