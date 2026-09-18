"""Prueba 4 - pipeline completo con boletin simulado y modelo simulado.

No llama a la API real ni sale a internet: sustituye el adaptador de boletin y
la funcion de llamada al modelo. Comprueba deduplicacion, exclusion de
descartados, generacion del HTML del correo y el mensaje de "sin novedades".

    .venv\\Scripts\\python.exe pruebas\\test_pipeline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

TEMPORAL = Path(tempfile.mkdtemp(prefix="mova-pipeline-"))
os.environ["MOVA_DATOS"] = str(TEMPORAL)
os.environ["MOVA_URL_PUBLICA"] = "http://boletines.interno:8770"

import config  # noqa: E402
from datos import repositorio  # noqa: E402
from integraciones import anthropic_cliente  # noqa: E402
from negocio import correo, deduplicador, orquestador, relevancia  # noqa: E402
from negocio.boletines import ADAPTADORES  # noqa: E402
from negocio.boletines.base import ErrorBoletin, PublicacionCruda  # noqa: E402

FECHA = date(2026, 9, 17)
fallos: list[str] = []


def comprobar(condicion: bool, mensaje: str) -> None:
    print(f"  {'OK   ' if condicion else 'FALLO'} {mensaje}")
    if not condicion:
        fallos.append(mensaje)


# ------------------------------------------------------- boletin simulado --
AYUDA_PYME = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo=("ORDEN 12/2026, de 15 de septiembre, por la que se aprueban las bases reguladoras "
            "y se convocan subvenciones para la modernizacion e inversion productiva de pymes "
            "industriales de la Comunitat Valenciana"),
    organismo="Conselleria de Innovacion, Industria, Comercio y Turismo",
    seccion="I. DISPOSICIONES GENERALES",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999001",
    url_pdf="https://dogv.gva.es/datos/2026/09/17/pdf/2026_99001_es.pdf",
    fecha="2026-09-17",
    texto=("Se convocan subvenciones en regimen de concurrencia competitiva para la "
           "modernizacion industrial y la inversion productiva de pequenas y medianas "
           "empresas. Beneficiarios: pymes industriales con centro de trabajo en la "
           "Comunitat Valenciana. Importe: 12.000.000 de euros. Plazo de solicitud: "
           "del 1 al 30 de octubre de 2026."),
    identificador="999001",
)

AYUDA_ASOCIACIONES = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo=("RESOLUCION de 14 de septiembre de 2026, por la que se convocan ayudas a "
            "asociaciones vecinales para actividades culturales"),
    organismo="Conselleria de Participacion",
    seccion="III. ACTOS ADMINISTRATIVOS",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999002",
    url_pdf="https://dogv.gva.es/datos/2026/09/17/pdf/2026_99002_es.pdf",
    fecha="2026-09-17",
    texto=("Ayudas dirigidas a asociaciones vecinales sin animo de lucro para actividades "
           "culturales de barrio. Beneficiarios: asociaciones vecinales inscritas. "
           "Importe: 150.000 euros."),
    identificador="999002",
)

NOMBRAMIENTO = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo="RESOLUCION de 12 de septiembre de 2026, de nombramiento de personal funcionario",
    organismo="Conselleria de Hacienda",
    seccion="II. AUTORIDADES Y PERSONAL",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999003",
    url_pdf="",
    fecha="2026-09-17",
    texto="Se nombra funcionaria de carrera. Sin contenido de ayudas ni subvenciones.",
    identificador="999003",
)

SIN_PALABRAS = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo="EDICTO sobre notificacion de expediente de deslinde de via pecuaria",
    organismo="Conselleria de Medio Ambiente",
    seccion="III. ACTOS ADMINISTRATIVOS",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999004",
    url_pdf="",
    fecha="2026-09-17",
    texto="Notificacion de deslinde. No menciona ningun termino del filtro.",
    identificador="999004",
)

_guion: dict[str, list] = {"publicaciones": []}


def _adaptador_simulado(fecha):  # noqa: ARG001 - la firma debe ser la del contrato
    return list(_guion["publicaciones"])


def _boletin_caido(fecha):  # noqa: ARG001
    raise ErrorBoletin("Simulacion: el boletin no responde")


# Convocatorias extra para las pruebas de alerta y de la tarde.
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
FIN_URGENTE = date.today() + timedelta(days=7)
TEXTO_FIN_URGENTE = f"hasta el {FIN_URGENTE.day} de {_MESES_ES[FIN_URGENTE.month - 1]} de {FIN_URGENTE.year}"

AYUDA_URGENTE = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo=("RESOLUCION de 16 de septiembre de 2026, por la que se convocan ayudas urgentes a la "
            "digitalizacion de pymes industriales del sector del calzado"),
    organismo="Conselleria de Innovacion, Industria, Comercio y Turismo",
    seccion="III. ACTOS ADMINISTRATIVOS",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999010",
    url_pdf="", fecha="2026-09-17",
    texto=f"Ayudas a pymes industriales del calzado. Plazo de solicitud: {TEXTO_FIN_URGENTE}.",
    identificador="999010",
)

AYUDA_EXTRAORDINARIA = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo=("DECRETO extraordinario 140/2026 por el que se aprueba un programa de ayudas a la "
            "eficiencia energetica de la industria afectada por la DANA"),
    organismo="Presidencia de la Generalitat",
    seccion="I. DISPOSICIONES GENERALES",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999020",
    url_pdf="", fecha="2026-09-17",
    texto="Programa de ayudas a la industria para eficiencia energetica. Numero extraordinario.",
    identificador="999020",
)

AYUDA_SIN_PRESUPUESTO = PublicacionCruda(
    codigo_boletin="DOGV",
    titulo="ORDEN 20/2026 por la que se convocan subvenciones a la internacionalizacion de pymes",
    organismo="Conselleria de Economia",
    seccion="I. DISPOSICIONES GENERALES",
    url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999030",
    url_pdf="", fecha="2026-09-17",
    texto="Subvenciones a la internacionalizacion de pymes.",
    identificador="999030",
)

# -------------------------------------------------------- modelo simulado --
LLAMADAS = {"n": 0}


def _modelo_simulado(sistema: str, mensaje: str, modelo: str, max_tokens: int,
                     **_opciones) -> dict:
    """Responde como Claude, sin red. Distingue extraccion de relevancia."""
    LLAMADAS["n"] += 1
    texto = mensaje.lower()
    es_pyme = "pyme" in texto or "industrial" in texto

    if "analista de convocatorias" in sistema.lower():
        titulo = ""
        for linea in mensaje.splitlines():
            if linea.startswith("TITULO SEGUN EL SUMARIO:"):
                titulo = linea.split(":", 1)[1].strip()
        if "nombramiento" in texto:
            return {"es_convocatoria_ayuda": False, "titulo": titulo, "resumen": "Nombramiento.",
                    "organismo_convocante": "Conselleria de Hacienda",
                    "plazo_solicitud": config.MARCADOR_PENDIENTE,
                    "beneficiarios": config.MARCADOR_PENDIENTE,
                    "importe": config.MARCADOR_PENDIENTE,
                    "confianza": "alta", "motivo_confianza": "Es un nombramiento de personal."}
        if "calzado" in texto:
            return {"es_convocatoria_ayuda": True, "titulo": titulo,
                    "titulo_resumido": "Ayudas a la digitalizacion de pymes del calzado",
                    "resumen": "Ayudas a la digitalizacion de pymes industriales del calzado.",
                    "organismo_convocante": "Conselleria de Innovacion, Industria, Comercio y Turismo",
                    "plazo_solicitud": TEXTO_FIN_URGENTE, "fecha_fin_plazo": FIN_URGENTE.isoformat(),
                    "beneficiarios": "Pymes industriales del calzado",
                    "importe": config.MARCADOR_PENDIENTE,
                    "confianza": "alta", "motivo_confianza": "El plazo figura en el texto."}
        if "extraordinario" in texto:
            return {"es_convocatoria_ayuda": True, "titulo": titulo,
                    "titulo_resumido": "Ayudas a la eficiencia energetica de la industria tras la DANA",
                    "resumen": "Programa de ayudas a la industria para eficiencia energetica.",
                    "organismo_convocante": "Presidencia de la Generalitat",
                    "plazo_solicitud": config.MARCADOR_PENDIENTE, "fecha_fin_plazo": None,
                    "beneficiarios": "Empresas industriales afectadas por la DANA",
                    "importe": config.MARCADOR_PENDIENTE,
                    "confianza": "media", "motivo_confianza": "No figura el plazo."}
        if es_pyme:
            return {"es_convocatoria_ayuda": True, "titulo": titulo,
                    "titulo_resumido": "Subvenciones a la modernizacion de pymes industriales",
                    "fecha_fin_plazo": "2026-10-30",
                    "resumen": "Subvenciones para modernizacion e inversion productiva de pymes "
                               "industriales de la Comunitat Valenciana.",
                    "organismo_convocante": "Conselleria de Innovacion, Industria, Comercio y Turismo",
                    "plazo_solicitud": "Del 1 al 30 de octubre de 2026",
                    "beneficiarios": "Pymes industriales con centro de trabajo en la Comunitat Valenciana",
                    "importe": "12.000.000 euros",
                    "confianza": "alta", "motivo_confianza": "Todos los datos figuran en el texto."}
        return {"es_convocatoria_ayuda": True, "titulo": titulo,
                "titulo_resumido": "Ayudas a asociaciones vecinales para actividades culturales",
                "fecha_fin_plazo": None,
                "resumen": "Ayudas a asociaciones vecinales para actividades culturales.",
                "organismo_convocante": "Conselleria de Participacion",
                "plazo_solicitud": config.MARCADOR_PENDIENTE,
                "beneficiarios": "Asociaciones vecinales sin animo de lucro",
                "importe": "150.000 euros",
                "confianza": "media", "motivo_confianza": "El plazo no aparece en el texto."}

    # Fase 4 - relevancia
    if es_pyme or "industria" in texto:
        return {"relevancia": "alta", "sectores": ["industria", "pyme"],
                "justificacion": "Dirigida expresamente a pymes industriales."}
    return {"relevancia": "baja", "sectores": ["cultura"],
            "justificacion": "Dirigida a asociaciones sin animo de lucro."}


def _esperar_fin(segundos: int = 90) -> None:
    import time

    limite = time.time() + segundos
    while orquestador.hay_ejecucion() and time.time() < limite:
        time.sleep(0.2)


def main() -> int:  # noqa: PLR0915 - es una prueba lineal, se lee mejor seguida
    print(f"Carpeta de datos de prueba: {config.DATOS}")
    repositorio.aplicar_esquema()
    repositorio.asegurar_admin_inicial()

    # Solo el boletin simulado: el resto se desactiva para no salir a internet.
    for fila in repositorio.boletines():
        repositorio.activar_boletin(fila["codigo"], fila["codigo"] == "DOGV")

    ADAPTADORES["DOGV"].obtener_publicaciones = _adaptador_simulado
    relevancia.anthropic_cliente.llamar_json = _modelo_simulado
    relevancia.anthropic_cliente.hay_clave = lambda: True
    orquestador.anthropic_cliente.hay_clave = lambda: True

    print("\n1) Primera ejecucion: 4 publicaciones, 2 son ayudas reales")
    _guion["publicaciones"] = [AYUDA_PYME, AYUDA_ASOCIACIONES, NOMBRAMIENTO, SIN_PALABRAS]
    aceptada, _ = orquestador.lanzar(FECHA, "manual", "prueba", enviar_correo=False)
    comprobar(aceptada, "la ejecucion se acepta")
    _esperar_fin()

    ejecucion = repositorio.ejecuciones(1)[0]
    comprobar(ejecucion["estado"] == "correcta", f"estado correcta (es {ejecucion['estado']})")
    comprobar(ejecucion["publicaciones_brutas"] == 4, "4 publicaciones brutas")
    comprobar(ejecucion["candidatas"] == 3,
              f"el filtro de palabras deja 3 candidatas (deja {ejecucion['candidatas']})")

    guardadas = repositorio.publicaciones({}, limite=50)
    comprobar(len(guardadas) == 2,
              f"se guardan 2 (el nombramiento lo descarta el modelo); hay {len(guardadas)}")

    pyme = next((p for p in guardadas if "pymes industriales" in p["titulo"]), None)
    comprobar(pyme is not None and pyme["relevancia"] == "alta", "la ayuda a pymes es alta")
    comprobar(pyme is not None and pyme["plazo"] == "Del 1 al 30 de octubre de 2026",
              "el plazo se extrae literal")
    asociaciones = next((p for p in guardadas if "asociaciones" in p["titulo"].lower()), None)
    comprobar(asociaciones is not None and asociaciones["relevancia"] == "baja",
              "la ayuda a asociaciones es baja")
    comprobar(asociaciones is not None and asociaciones["plazo"] == config.MARCADOR_PENDIENTE,
              f"el plazo que no consta se guarda como {config.MARCADOR_PENDIENTE}")

    print("\n2) Segunda ejecucion identica: la deduplicacion evita repetir")
    llamadas_antes = LLAMADAS["n"]
    orquestador.lanzar(FECHA, "manual", "prueba", enviar_correo=False)
    _esperar_fin()
    comprobar(len(repositorio.publicaciones({}, limite=50)) == 2,
              "no se anade ninguna publicacion repetida")
    comprobar(LLAMADAS["n"] == llamadas_antes,
              "no se gasta ni una llamada al modelo con los duplicados")

    print("\n3) Deduplicacion difusa: mismo titulo con retoques menores")
    variante = PublicacionCruda(**{**AYUDA_PYME.__dict__,
                                  "titulo": AYUDA_PYME.titulo.replace("ORDEN 12/2026", "Orden 12/2026 ")
                                            + ".",
                                  "identificador": "999005"})
    veredicto = deduplicador.comprobar(
        "DOGV", variante.titulo, deduplicador.calcular_hash("DOGV", variante.titulo), False,
        [dict(f) for f in repositorio.titulos_recientes(30)], 92)
    comprobar(veredicto.duplicada, f"la variante se detecta como duplicada ({veredicto.similitud}%)")

    print("\n4) Lo descartado no vuelve a entrar")
    repositorio.descartar(pyme["id"], "correo", destinatario="antonio@mova.es", ip="127.0.0.1")
    comprobar(repositorio.publicacion(pyme["id"])["estado"] == "descartada",
              "la publicacion queda marcada como descartada")
    hash_pyme = pyme["hash_contenido"]
    comprobar(repositorio.existe_hash(hash_pyme), "su hash sigue bloqueado tras el descarte")

    _guion["publicaciones"] = [AYUDA_PYME]
    orquestador.lanzar(FECHA, "manual", "prueba", enviar_correo=False)
    _esperar_fin()
    descartada = [p for p in repositorio.publicaciones({}, limite=50)
                  if p["hash_contenido"] == hash_pyme]
    comprobar(len(descartada) == 1 and descartada[0]["estado"] == "descartada",
              "la publicacion descartada no se vuelve a guardar")

    print("\n5) El correo diario se genera con su estructura")
    filas = [dict(f) for f in repositorio.publicaciones_por_ids(
        [p["id"] for p in repositorio.publicaciones({}, limite=50)])]
    tokens = {fila["id"]: repositorio.crear_token_descarte(fila["id"], "antonio@mova.es", 90)
              for fila in filas}
    # Una segunda comunidad, para comprobar que el correo agrupa bien.
    filas.append({**filas[0], "id": 9999, "comunidad": "Andalucia", "codigo_boletin": "BOJA",
                  "boletin_nombre": "Boletin Oficial de la Junta de Andalucia",
                  "titulo": "Orden de 16 de septiembre de 2026, de incentivos a la digitalizacion "
                            "de la pyme andaluza", "relevancia": "alta"})
    tokens[9999] = repositorio.crear_token_descarte(filas[0]["id"], "j.javier@mova.es", 90)

    html = correo.componer(filas, FECHA,
                           {"consultados": ["DOGV", "BOJA"],
                            "fallidos": [{"codigo": "BORM", "motivo": "reto anti-bot"}]}, tokens)
    comprobar("Comunidad Valenciana" in html and "Andalucia" in html,
              "el correo lleva cabecera por comunidad autonoma")
    comprobar("ALTA RELEVANCIA" in html, "el correo marca las de alta relevancia")
    comprobar(html.count("Descartar esta publicacion") >= 2,
              "cada publicacion lleva su enlace de descarte")
    comprobar("/descartar/" in html, "los enlaces de descarte apuntan a la ruta con token")
    comprobar("BORM" in html and "anti-bot" in html,
              "el correo dice expresamente que boletin ha fallado")
    comprobar("<table" in html and "flex" not in html.lower(),
              "el HTML usa tablas y no flexbox (compatible con Outlook)")
    comprobar("http://" not in html.replace("http://boletines.interno:8770", "")
              .replace("http://www.juntadeandalucia.es", "")
              or "<img" not in html, "no hay imagenes externas incrustadas")

    ruta = correo.guardar_copia(html, "correo_ejemplo.html")
    comprobar(ruta.exists() and ruta.stat().st_size > 2000,
              f"correo de ejemplo escrito en {ruta}")

    print("\n6) Sin resultados: el correo dice exactamente el texto acordado")
    vacio = correo.componer([], FECHA, {"consultados": ["DOGV"], "fallidos": []})
    comprobar(correo.SIN_NOVEDADES in vacio,
              "aparece 'No se han encontrado nuevas ayudas o subvenciones en los boletines revisados'")
    comprobar(correo.asunto(FECHA, 0, 0).endswith("sin novedades"),
              "el asunto refleja que no hay novedades")

    print("\n7) Un boletin caido no tumba la ejecucion")
    repositorio.activar_boletin("BOJA", True)
    ADAPTADORES["BOJA"].obtener_publicaciones = _boletin_caido
    _guion["publicaciones"] = [AYUDA_ASOCIACIONES]
    orquestador.lanzar(date(2026, 9, 18), "manual", "prueba", enviar_correo=False)
    _esperar_fin()
    ultima = repositorio.ejecuciones(1)[0]
    comprobar(ultima["estado"] == "con_avisos",
              f"la ejecucion termina con avisos (es {ultima['estado']})")
    comprobar(ultima["boletines_fallidos"] == 1 and ultima["boletines_ok"] == 1,
              "un boletin falla y el otro se procesa igualmente")
    logs = repositorio.logs_scraping(ultima["id"])
    comprobar(any(log["codigo_boletin"] == "BOJA" and log["estado"] == "error" for log in logs),
              "el fallo del boletin queda trazado en logs_scraping")

    print("\n8) Bucle de calidad: respuesta mala del modelo")
    def _modelo_malo(sistema, mensaje, modelo, max_tokens, **_opciones):
        return {"titulo": "", "resumen": "linea1\nlinea2\nlinea3\nlinea4\nlinea5\nlinea6",
                "organismo_convocante": "no disponible", "plazo_solicitud": "no consta",
                "beneficiarios": "", "importe": "", "confianza": "altisima",
                "motivo_confianza": "", "es_convocatoria_ayuda": True}

    problemas = relevancia.validar(_modelo_malo("", "", "", 0))
    comprobar(len(problemas) >= 4, f"el validador detecta los problemas ({len(problemas)})")
    resultado = relevancia.extraer(
        {"titulo": "Convocatoria de ayudas", "texto": "texto", "organismo": "Organismo"},
        "modelo-simulado", 2000, llamar=_modelo_malo)
    comprobar(resultado.revision_manual, "tras dos intentos se marca para revision manual")
    comprobar(resultado.llamadas == 2, "se reintenta una sola vez (2 llamadas en total)")
    comprobar(resultado.datos["titulo"] == "Convocatoria de ayudas",
              "el titulo se rescata del sumario en vez de quedar vacio")
    comprobar(resultado.datos["plazo_solicitud"] == config.MARCADOR_PENDIENTE,
              "los textos genericos se sustituyen por el marcador, nunca por datos inventados")


    # ---------------------------------------------------------- v1.1 --
    ENVIADOS: list[dict] = []

    def _enviar_simulado(destinatarios, asunto, html, reintentos=3, urgente=False):
        ENVIADOS.append({"asunto": asunto, "html": html, "urgente": urgente,
                         "destinatarios": list(destinatarios)})
        return True, f"Enviado a {len(destinatarios)} destinatario(s)", 1

    correo.enviar = _enviar_simulado
    repositorio.activar_boletin("BOJA", False)

    print("\n9) Titulo resumido y fin de plazo")
    pyme = repositorio.publicacion(pyme["id"])
    comprobar(pyme["titulo_resumido"] == "Subvenciones a la modernizacion de pymes industriales",
              "se guarda el titulo resumido que da el modelo")
    comprobar(pyme["titulo"].startswith("ORDEN 12/2026"),
              "y se conserva el titulo oficial literal")
    comprobar(pyme["plazo_fin"] == "2026-10-30" and pyme["plazo_fin_origen"] == "fecha_literal",
              f"el fin de plazo sale del texto: {pyme['plazo_fin']} ({pyme['plazo_fin_origen']})")
    asociaciones = repositorio.publicacion(asociaciones["id"])
    comprobar(asociaciones["plazo_fin"] is None,
              "sin plazo en el texto no se inventa fecha de fin")

    print("\n10) Alerta inmediata por plazo corto")
    _guion["publicaciones"] = [AYUDA_URGENTE]
    ENVIADOS.clear()
    orquestador.lanzar(FECHA, "manual", "prueba", enviar_correo=True)
    _esperar_fin()
    urgentes = [e for e in ENVIADOS if e["urgente"]]
    comprobar(len(urgentes) == 1 and urgentes[0]["asunto"].startswith("[URGENTE]"),
              "se envia un correo urgente aparte")
    comprobar(bool(urgentes) and "Ayudas a la digitalizacion de pymes del calzado" in urgentes[0]["html"],
              "la alerta lleva el titulo resumido")
    comprobar(bool(urgentes) and "Vence el" in urgentes[0]["html"],
              "la alerta dice cuando vence el plazo")
    comprobar(len(ENVIADOS) == 2 and not ENVIADOS[1]["urgente"],
              "y despues sale el correo diario normal")
    urgente = [p for p in repositorio.publicaciones({}, limite=50) if "calzado" in p["titulo"]][0]
    comprobar(urgente["alerta_enviada"] == 1, "la publicacion queda marcada como alertada")

    print("\n11) Comprobacion de la tarde sin novedades: no escribe")
    ENVIADOS.clear()
    orquestador.lanzar(FECHA, "tarde", "planificador", enviar_correo=True)
    _esperar_fin()
    comprobar(not ENVIADOS, "sin publicaciones nuevas no se envia ningun correo")
    ultimo_envio = repositorio.envios(1)[0]
    comprobar(ultimo_envio["estado"] == "omitido" and "tarde" in ultimo_envio["asunto"].lower(),
              "queda trazado que la comprobacion de la tarde no envio nada")

    print("\n12) Comprobacion de la tarde con un boletin extraordinario")
    _guion["publicaciones"] = [AYUDA_URGENTE, AYUDA_EXTRAORDINARIA]
    ENVIADOS.clear()
    orquestador.lanzar(FECHA, "tarde", "planificador", enviar_correo=True)
    _esperar_fin()
    comprobar(len(ENVIADOS) == 1, f"se envia un unico correo ({len(ENVIADOS)})")
    if ENVIADOS:
        comprobar("comprobacion de la tarde" in ENVIADOS[0]["asunto"],
                  "con asunto de comprobacion de la tarde")
        comprobar("eficiencia energetica de la industria" in ENVIADOS[0]["html"],
                  "con la publicacion extraordinaria")
        comprobar("calzado" not in ENVIADOS[0]["html"],
                  "y sin repetir lo que ya se envio por la manana")

    print("\n13) Resumen semanal")
    repositorio.guardar_ajuste("dias_vencimiento_semanal", "60")
    ENVIADOS.clear()
    exito, _ = orquestador.enviar_resumen_semanal(hoy=date(2026, 9, 21), usuario="prueba")
    comprobar(exito and len(ENVIADOS) == 1, "el resumen semanal se envia")
    if ENVIADOS:
        html = ENVIADOS[0]["html"]
        comprobar("Resumen semanal" in ENVIADOS[0]["asunto"], "con su asunto")
        comprobar("14 de septiembre de 2026" in html and "20 de septiembre de 2026" in html,
                  "cubre la semana anterior de lunes a domingo")
        comprobar("Ayudas a la digitalizacion de pymes del calzado" in html,
                  "recoge lo publicado esa semana")
        comprobar("Subvenciones a la modernizacion de pymes industriales" not in html,
                  "sin lo que se descarto (la de pymes del paso 4)")
        comprobar("Ayudas a asociaciones vecinales" not in html.split("Alta relevancia")[1].split("Resto")[0],
                  "las de relevancia baja no se mezclan con las de alta")

    # Los vencimientos se cuentan desde el dia real, igual que en produccion.
    ENVIADOS.clear()
    orquestador.enviar_resumen_semanal(hoy=date.today(), usuario="prueba")
    if ENVIADOS:
        comprobar("Plazos que vencen" in ENVIADOS[0]["html"]
                  and FIN_URGENTE.strftime("%d/%m/%Y") in ENVIADOS[0]["html"],
                  "y lista los plazos que vencen en los proximos dias")

    print("\n14) Coste: tokens, precio, esfuerzo y tope mensual")
    PETICIONES: list[dict] = []
    RESPUESTA = {"motivo": "end_turn"}

    class _Mensajes:
        def create(self, **parametros):
            PETICIONES.append(parametros)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"relevancia": "alta"}')],
                usage=SimpleNamespace(input_tokens=1000, output_tokens=200,
                                      cache_read_input_tokens=0, cache_creation_input_tokens=0),
                stop_reason=RESPUESTA["motivo"])

    anthropic_cliente._cliente = lambda: SimpleNamespace(messages=_Mensajes())
    repositorio.guardar_ajuste("tope_mensual_usd", "30")
    gasto_antes = repositorio.gasto_mes_usd()

    anthropic_cliente.llamar("s", "m", "claude-sonnet-5", 2000, fase="extraccion")
    comprobar(PETICIONES[-1].get("output_config") == {"effort": "low"},
              "a Sonnet 5 se le pide esfuerzo bajo (razona por defecto)")
    anthropic_cliente.llamar("s", "m", "claude-haiku-4-5-20251001", 600, fase="relevancia")
    comprobar("output_config" not in PETICIONES[-1],
              "a Haiku 4.5 no se le manda (no lo admite)")

    gasto = repositorio.gasto_mes_usd() - gasto_antes
    esperado = (1000 * 2 + 200 * 10) / 1e6 + (1000 * 1 + 200 * 5) / 1e6
    comprobar(abs(gasto - esperado) < 1e-9,
              f"el coste se calcula con la tarifa de cada modelo ({gasto:.6f} $)")
    por_modelo = {f["modelo"]: f for f in repositorio.consumo_por_modelo()}
    comprobar(por_modelo.get("claude-sonnet-5") is not None
              and por_modelo["claude-sonnet-5"]["entrada"] == 1000,
              "cada llamada queda registrada con sus tokens")

    RESPUESTA["motivo"] = "max_tokens"
    try:
        anthropic_cliente.llamar("s", "m", "claude-sonnet-5", 2000, fase="extraccion")
        cortada = False
    except anthropic_cliente.ErrorModelo as error:
        cortada = "limite de tokens" in str(error)
    comprobar(cortada, "una respuesta cortada por max_tokens da un error claro")
    comprobar(repositorio.gasto_mes_usd() - gasto_antes > esperado,
              "y sus tokens se contabilizan igualmente (se facturan)")
    RESPUESTA["motivo"] = "end_turn"

    repositorio.guardar_ajuste("tope_mensual_usd", "0.001")
    try:
        anthropic_cliente.llamar("s", "m", "claude-sonnet-5", 2000)
        bloqueada = False
    except anthropic_cliente.TopeAlcanzado:
        bloqueada = True
    comprobar(bloqueada, "con el tope superado no se hace ninguna llamada mas")

    print("\n15) Con el tope alcanzado, la vigilancia sigue pero sin gastar")
    llamadas_antes = LLAMADAS["n"]
    relevancia.anthropic_cliente.hay_clave = lambda: True
    _guion["publicaciones"] = [AYUDA_SIN_PRESUPUESTO]
    orquestador.lanzar(FECHA, "manual", "prueba", enviar_correo=False)
    _esperar_fin()
    guardada = [p for p in repositorio.publicaciones({}, limite=80)
                if "internacionalizacion" in p["titulo"]]
    comprobar(len(guardada) == 1, "la publicacion se recoge igualmente")
    comprobar(bool(guardada) and guardada[0]["revision_manual"] == 1
              and "Tope de gasto" in guardada[0]["motivo_revision"],
              "marcada para revision manual por el tope de gasto")
    comprobar(LLAMADAS["n"] == llamadas_antes, "sin ninguna llamada al modelo")
    comprobar(bool(guardada) and guardada[0]["titulo_resumido"] != "",
              "y aun asi con titulo resumido (respaldo sin IA)")
    repositorio.guardar_ajuste("tope_mensual_usd", "30")

    print(f"\n{'TODAS LAS COMPROBACIONES PASAN' if not fallos else 'FALLOS: ' + str(fallos)}")
    print(f"Llamadas simuladas al modelo: {LLAMADAS['n']}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
