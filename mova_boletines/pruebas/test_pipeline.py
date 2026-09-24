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
os.environ["MOVA_RECUPERACION"] = "0"  # se prueba llamando a mano, no con el reloj

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
        destinos = {"estudiantes": "personas", "ayuntamientos y empresas": "publico",
                     "ayuntamientos": "publico", "fundaciones": "privado"}
        for clave, destino in destinos.items():
            if clave in texto:
                return {"es_convocatoria_ayuda": True, "titulo": titulo,
                        "titulo_resumido": f"Ayudas de prueba para {clave}",
                        "resumen": f"Ayudas de prueba dirigidas a {clave}.",
                        "organismo_convocante": "Conselleria de Prueba",
                        "plazo_solicitud": config.MARCADOR_PENDIENTE, "fecha_fin_plazo": None,
                        "beneficiarios": clave.capitalize(), "destinatario": destino,
                        "importe": config.MARCADOR_PENDIENTE,
                        "confianza": "media", "motivo_confianza": "Prueba."}
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
    comprobar(ejecucion["candidatas"] == 2,
              f"quedan 2 candidatas: el nombramiento se aparta sin pagar al modelo "
              f"(quedan {ejecucion['candidatas']})")

    guardadas = repositorio.publicaciones({}, limite=50)
    comprobar(len(guardadas) == 2, f"se guardan las 2 ayudas; hay {len(guardadas)}")

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
    comprobar("ALTA RELEVANCIA" not in html,
              "el correo ya no lleva etiqueta de relevancia (el usuario la quito)")
    comprobar(">Publicacion oficial<" in html and ">PDF oficial<" in html
              and ">Comunidad<" not in html and ">Boletin<" not in html
              and ">Fecha publicacion<" not in html and ">Enlaces<" not in html,
              "la ficha deja titulo, organismo y botones")
    comprobar(html.count("Descartar esta publicacion") >= 2,
              "cada publicacion lleva su enlace de descarte")
    comprobar("/descartar/" in html, "los enlaces de descarte apuntan a la ruta con token")
    comprobar("BORM" in html and "anti-bot" in html,
              "el correo dice expresamente que boletin ha fallado")
    comprobar("<table" in html and "flex" not in html.lower(),
              "el HTML usa tablas y no flexbox (compatible con Outlook)")
    comprobar('src="http' not in html and "cid:logo-mova" in html,
              "el logotipo va incrustado (cid), sin imagenes que se bajen de internet")
    comprobar("data:image/png;base64," in correo.logo_incrustado(html),
              "y en la copia que se guarda se ve, con la imagen dentro del fichero")

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

    semanal_html = correo.componer_semanal(FECHA, FECHA, [], [], 30, FECHA)
    comprobar("cid:logo-mova" in semanal_html,
              "el resumen semanal lleva el mismo logotipo que el correo diario")

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

    print("\n16) Solo entra lo publicado el dia vigilado")
    del_dia_anterior = PublicacionCruda(
        codigo_boletin="DOGV",
        titulo="ORDEN 30/2026 por la que se convocan ayudas a pymes publicada el dia anterior",
        organismo="Conselleria de Economia", seccion="I. DISPOSICIONES GENERALES",
        url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999040", url_pdf="",
        fecha=(FECHA - timedelta(days=1)).isoformat(),
        texto="Ayudas a pymes.", identificador="999040")
    del_dia = PublicacionCruda(
        codigo_boletin="DOGV",
        titulo="ORDEN 31/2026 por la que se convocan ayudas a la innovacion de pymes del dia",
        organismo="Conselleria de Economia", seccion="I. DISPOSICIONES GENERALES",
        url_oficial="https://dogv.gva.es/es/disposicio-canonica?sig=999041", url_pdf="",
        fecha=FECHA.isoformat(), texto="Ayudas a la innovacion de pymes.", identificador="999041")
    _guion["publicaciones"] = [del_dia_anterior, del_dia]
    ENVIADOS.clear()
    orquestador.lanzar(FECHA, "manual", "prueba", enviar_correo=True)
    _esperar_fin()
    diario = [e for e in ENVIADOS if not e["urgente"]]
    comprobar(bool(diario) and "innovacion de pymes del dia" in diario[0]["html"],
              "la publicacion del dia llega al correo")
    comprobar(bool(diario) and "publicada el dia anterior" not in diario[0]["html"],
              "la de un dia anterior NO llega al correo")
    comprobar(not any("publicada el dia anterior" in p["titulo"]
                      for p in repositorio.publicaciones({}, limite=100)),
              "ni se guarda en el historico como si fuera de hoy")
    registro_ejecucion = repositorio.ejecuciones(1)[0]["registro"]
    comprobar("de otra fecha" in registro_ejecucion and "descartadas" in registro_ejecucion,
              "y el descarte queda anotado en el registro de la ejecucion")

    print("\n17) El correo ya no lleva resumen, plazo, beneficiarios ni importe")
    html_dia = diario[0]["html"] if diario else ""
    for campo in (">Resumen<", ">Plazo<", ">Beneficiarios<", ">Importe<"):
        comprobar(campo not in html_dia, f"sin el campo {campo.strip('><')}")
    import re as _re
    comprobar(all(_re.search(rf"/d/[A-Za-z0-9_-]{{20,}}/{tipo}\"", html_dia)
                  for tipo in ("corto", "ampliado", "infografia")),
              "cada ficha lleva los botones Resumen corto, Resumen ampliado e Infografia "
              "con enlace de clave (no piden iniciar sesion)")

    print("\n18) Resumen corto, ampliado e infografia")
    from negocio import documentos

    DATOS_BASES = {
        "nombre_ayuda": "Ayudas a la innovacion de pymes 2026", "organismo": "Conselleria de Economia",
        "ambito": "Comunitat Valenciana", "regimen": "Concurrencia competitiva",
        "claim": "Hasta 200.000 euros para innovar", "objeto": "Financiar proyectos de innovacion.",
        "beneficiarios": "Pymes con sede en la Comunitat Valenciana <script>alert(1)</script>",
        "benef_corto": "Pymes valencianas", "exclusiones": "Empresas en crisis",
        "actuaciones": [{"actuacion": "Desarrollo de producto", "descripcion": "prototipos"},
                        "Digitalizacion de procesos"],
        "gastos_elegibles": ["Personal tecnico", "Equipos"], "gastos_excluidos": [],
        "cuantia_max": "200.000 €", "cuantia_min": None, "intensidad": "50%",
        "inversion_min": "20.000 €", "inversion_max": None, "credito": "3.000.000 €",
        "criterios": [{"criterio": "Grado de innovacion", "puntos": "40", "descripcion": "novedad"}],
        "doc_solicitud": ["Memoria tecnica"], "doc_justificacion": ["Facturas"],
        "plazo_inicio": "01/10/2026", "plazo_fin": "30/10/2026",
        "plazo_ejecucion": "desde 01/01/2026 hasta 31/12/2026", "plazo_justificacion": "31/01/2027",
        "ejecucion_pago": None, "compatibilidades": None, "incompatibilidades": None,
        "referencias": ["Orden 31/2026"], "enlaces": [], "cierre": None, "alertas": [],
        "fuentes": {"cuantia_max": "Art. 7, pag. 3"}}
    PETICIONES_DOC: list[dict] = []

    def _texto_simulado(publicacion):
        return ("[Página 1]\nBases reguladoras. " + "Texto de la convocatoria. " * 40,
                "https://dogv.gva.es/datos/simulado.pdf", 3, False)

    def _ia_documentos(sistema, mensaje, modelo, max_tokens, **opciones):
        PETICIONES_DOC.append({"sistema": sistema, "mensaje": mensaje, "modelo": modelo,
                               "max_tokens": max_tokens, **opciones})
        return dict(DATOS_BASES)

    documentos.texto_de_publicacion = _texto_simulado
    anthropic_cliente.llamar_json = _ia_documentos
    anthropic_cliente.hay_clave = lambda: True

    publicacion_doc = next(p for p in repositorio.publicaciones({}, limite=100)
                           if "innovacion de pymes del dia" in p["titulo"])
    datos, meta = documentos.extraer_datos(dict(publicacion_doc))
    comprobar(len(PETICIONES_DOC) == 1 and PETICIONES_DOC[0]["fase"] == "documentos",
              "una sola llamada a la IA para los tres documentos")
    comprobar("DOCUMENTACIÓN OFICIAL APORTADA" in PETICIONES_DOC[0]["sistema"]
              and "[Página 1]" in PETICIONES_DOC[0]["sistema"],
              "se le manda el texto integro del PDF con marcas de pagina")
    comprobar("gastos_elegibles" in PETICIONES_DOC[0]["mensaje"]
              and "RÉGIMEN DE MINIMIS" in PETICIONES_DOC[0]["mensaje"],
              "con las mismas instrucciones que Resumen Ayudas")
    comprobar(PETICIONES_DOC[0]["modelo"] == "claude-sonnet-5" and PETICIONES_DOC[0]["max_tokens"] == 16000,
              "con Sonnet 5 y 16.000 tokens por defecto")
    comprobar(publicacion_doc["url_oficial"] in datos["enlaces"],
              "el enlace oficial se anade aunque la IA no lo cite")

    corto = documentos.renderizar("corto", datos, dict(publicacion_doc))
    comprobar(all(t in corto for t in ("Nombre/objeto del trámite:", "Beneficiarios:",
                                       "Actuaciones Apoyables:", "Costes Apoyables:",
                                       "Tipo de Ayuda y Cuantía:", "Plazo:")),
              "resumen corto con sus apartados")
    comprobar("Hasta el 50% con una cuantía máxima de 200.000 €." in corto
              and "Finaliza el 30 de octubre de 2026." in corto,
              "redacta cuantia y plazo como Resumen Ayudas")
    comprobar("Desarrollo de producto: prototipos" in corto,
              "las actuaciones en forma de objeto se leen bien")
    comprobar(corto.count("data:image/png;base64,") == 2 and "info@mova.es" in corto,
              "con logotipo, edificio de fondo y pie del membrete MOVA")
    comprobar("<script>alert(1)</script>" not in corto and "&lt;script&gt;" in corto,
              "el texto de la IA se escapa (no se puede inyectar HTML)")

    ampliado = documentos.renderizar("ampliado", datos, dict(publicacion_doc))
    comprobar(all(t in ampliado for t in ("Exclusiones:", "Criterios de valoración:",
                                          "Documentación con la solicitud:",
                                          "Documentación de justificación:",
                                          "Plazos de ejecución y justificación:",
                                          "Crédito presupuestario:", "Referencias y enlaces:")),
              "resumen ampliado con sus apartados")
    comprobar("Grado de innovacion" in ampliado and "(40)" in ampliado,
              "los criterios salen con su puntuacion")

    infografia = documentos.renderizar("infografia", datos, dict(publicacion_doc))
    comprobar("Datos clave" in infografia and "200.000 €" in infografia and "50%" in infografia,
              "infografia con los datos clave")
    comprobar("barra-mova" not in infografia, "la version para descargar no lleva la barra")

    print("\n19) Los botones dentro de la aplicacion")
    import app as aplicacion_mova

    web = aplicacion_mova.crear_aplicacion()
    web.config["TESTING"] = True
    cliente = web.test_client()
    cliente.post("/login", data={"usuario": "admin", "clave": "MovaBoletines2026"})
    cliente.post("/cambiar-clave", data={"actual": "MovaBoletines2026", "nueva": "PruebaDocs2026!",
                                         "repetida": "PruebaDocs2026!"})
    ruta = f"/publicaciones/{publicacion_doc['id']}/documento"
    PETICIONES_DOC.clear()
    primera = cliente.get(f"{ruta}/corto")
    comprobar(primera.status_code == 200 and "Analizando la publicacion" in primera.get_data(as_text=True),
              "al pulsar el boton se lanza el analisis y se muestra 'generando'")
    import time as _time
    for _ in range(50):
        if not documentos.generando(publicacion_doc["id"]):
            break
        _time.sleep(0.1)
    lista = cliente.get(f"{ruta}/corto").get_data(as_text=True)
    comprobar("Nombre/objeto del trámite:" in lista and "barra-mova" in lista,
              "despues se muestra el documento con su barra")
    cliente.get(f"{ruta}/ampliado")
    cliente.get(f"{ruta}/infografia")
    comprobar(len(PETICIONES_DOC) == 1,
              "abrir los otros dos documentos no vuelve a llamar a la IA")
    descarga = cliente.get(f"{ruta}/infografia/descargar")
    comprobar("attachment" in descarga.headers.get("Content-Disposition", "")
              and "Infografia-" in descarga.headers.get("Content-Disposition", ""),
              "se puede descargar el documento")
    from negocio import pdf as _pdf
    if _pdf.navegador():
        disposicion = descarga.headers.get("Content-Disposition", "")
        comprobar(descarga.mimetype == "application/pdf" and descarga.data.startswith(b"%PDF")
                  and disposicion.endswith('.pdf"'),
                  "y se descarga en PDF, no en HTML")
    else:
        print("   (sin Edge ni Chrome en este equipo: no se comprueba el PDF)")
    tabla = cliente.get("/publicaciones").get_data(as_text=True)
    comprobar("Resumen corto" in tabla and ">listos<" in tabla,
              "la tabla de publicaciones muestra los botones y que ya estan generados")
    comprobar(">Plazo<" not in tabla and ">Beneficiarios<" not in tabla and ">Importe<" not in tabla,
              "y ya no tiene las columnas de plazo, beneficiarios e importe")
    print("\n20) Quien recibe el correo genera los documentos sin iniciar sesion")
    anonimo = web.test_client()
    otra = next(p for p in repositorio.publicaciones({}, limite=100) if "DANA" in p["titulo"])
    clave = repositorio.token_documento_para(otra["id"], 90)
    comprobar(repositorio.token_documento_para(otra["id"], 90) == clave,
              "la misma publicacion reutiliza su enlace (diario, alerta y semanal coinciden)")
    PETICIONES_DOC.clear()
    primera = anonimo.get(f"/d/{clave}/ampliado").get_data(as_text=True)
    comprobar("Generando el resumen ampliado" in primera,
              "sin sesion, el boton del correo lanza el analisis y dice 'Generando'")
    comprobar("Analizando la publicacion" not in primera and "IA" not in primera
              and "barra-progreso" not in primera and "Publicaciones" not in primera,
              "sin mostrar el proceso ni la herramienta")
    for _ in range(50):
        if not documentos.generando(otra["id"]):
            break
        _time.sleep(0.1)
    estado_listo = anonimo.get(f"/d/{clave}/ampliado/listo").get_json()
    comprobar(estado_listo == {"listo": True, "error": False},
              "la pagina de espera sabe cuando ya esta el documento")
    comprobar(anonimo.get("/d/claveInventadaQueNoExiste1234567/ampliado/listo").status_code == 404,
              "y esa consulta no responde a un enlace inventado")
    usos_antes = repositorio.token_documento(clave)["usos"]
    for _ in range(5):
        anonimo.get(f"/d/{clave}/ampliado/listo")
    comprobar(repositorio.token_documento(clave)["usos"] == usos_antes,
              "preguntar si ya esta no cuenta como abrir el enlace")
    comprobar(repositorio.intentos_recientes("127.0.0.1", 10, "documento_espera") >= 5,
              "esas consultas van a su propio contador, no al de las aperturas")
    listo = anonimo.get(f"/d/{clave}/ampliado").get_data(as_text=True)
    comprobar("Criterios de valoración:" in listo and "barra-mova" in listo,
              "y luego muestra el documento")
    comprobar("Regenerar" not in listo and "&larr; Publicaciones" not in listo,
              "sin boton de regenerar ni acceso a la aplicacion")
    anonimo.get(f"/d/{clave}/corto")
    anonimo.get(f"/d/{clave}/infografia")
    comprobar(len(PETICIONES_DOC) == 1, "los tres documentos cuestan una sola llamada")
    descarga = anonimo.get(f"/d/{clave}/corto/descargar")
    comprobar("attachment" in descarga.headers.get("Content-Disposition", ""),
              "puede descargarlos")
    if _pdf.navegador():
        comprobar(descarga.mimetype == "application/pdf" and descarga.data.startswith(b"%PDF"),
                  "tambien en PDF")
    comprobar(anonimo.get("/publicaciones").status_code == 302,
              "la clave no abre el resto de la herramienta")
    falsa = anonimo.get("/d/claveInventadaQueNoExiste1234567/corto")
    comprobar(falsa.status_code == 404 and "no es valido" in falsa.get_data(as_text=True),
              "un enlace inventado no abre nada")
    comprobar(repositorio.token_documento(clave)["usos"] >= 4,
              "cada uso queda registrado")

    print("\n21) Clave de API pegada dos veces")
    buena = "sk-ant-api03-" + "Q" * 95
    limpia, aviso = anthropic_cliente.normalizar_clave(buena + buena)
    comprobar(limpia == buena and "2 veces" in aviso, "al guardar se deja una sola copia y se avisa")
    try:
        anthropic_cliente.normalizar_clave(buena + "sk-ant-api03-" + "Z" * 95)
        distintas = False
    except anthropic_cliente.ErrorModelo:
        distintas = True
    comprobar(distintas, "dos claves distintas juntas se rechazan")
    repositorio.guardar_ajuste("anthropic_api_key", buena + buena)
    comprobar(anthropic_cliente.corregir_clave_guardada()
              and repositorio.ajuste("anthropic_api_key") == buena,
              "una clave ya guardada duplicada se corrige sola al arrancar")

    print("\n22) Si el equipo estaba apagado, lo pendiente se hace al encenderlo")
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    from negocio import recuperacion

    madrid = ZoneInfo("Europe/Madrid")
    for clave, valor in {"dias_ejecucion": "mon-sun", "hora_ejecucion": "07:45",
                         "hora_tarde": "20:00", "tarde_activa": "1", "planificador_activo": "1",
                         "recuperacion_activa": "1", "dias_recuperacion": "7",
                         "recuperacion_desde": "2030-01-13", "zona_horaria": "Europe/Madrid",
                         "semanal_activo": "1", "dia_semanal": "mon",
                         "hora_semanal": "08:30"}.items():
        repositorio.guardar_ajuste(clave, valor)
    ahora = _dt(2030, 1, 16, 10, 0, tzinfo=madrid)  # miercoles por la manana
    lista = recuperacion.pendientes(ahora)
    comprobar(lista[:2] == [(date(2030, 1, 13), "recuperada"), (date(2030, 1, 13), "tarde_recuperada")]
              and lista[-1] == (date(2030, 1, 16), "recuperada") and len(lista) == 7,
              f"apagado desde el domingo: 4 mananas y 3 tardes pendientes, la mas antigua primero ({len(lista)})")
    comprobar((date(2030, 1, 16), "tarde_recuperada") not in lista,
              "la tarde de hoy aun no toca")

    buena = repositorio.crear_ejecucion("2030-01-14", "manual", "prueba")
    repositorio.cerrar_ejecucion(buena, "correcta", "", "", {"boletines_ok": 7})
    lista = recuperacion.pendientes(ahora)
    comprobar((date(2030, 1, 14), "recuperada") not in lista,
              "un dia ya vigilado (aunque sea a mano) no se repite")
    comprobar((date(2030, 1, 14), "tarde_recuperada") in lista,
              "pero su tarde si, porque esa ejecucion empezo antes de las 20:00")

    sin_red = repositorio.crear_ejecucion("2030-01-15", "programada", "planificador")
    repositorio.cerrar_ejecucion(sin_red, "con_avisos", "", "", {"boletines_ok": 0,
                                                                 "boletines_fallidos": 7})
    comprobar((date(2030, 1, 15), "recuperada") in recuperacion.pendientes(ahora),
              "una ejecucion sin ningun boletin consultado (sin red) no cuenta como hecha")
    for _ in range(recuperacion.INTENTOS_MAX):
        fallida = repositorio.crear_ejecucion("2030-01-15", "recuperada", "recuperacion")
        repositorio.cerrar_ejecucion(fallida, "error", "", "", {})
    comprobar((date(2030, 1, 15), "recuperada") not in recuperacion.pendientes(ahora),
              "tras 3 intentos fallidos se deja de insistir")

    en_curso = repositorio.crear_ejecucion("2030-01-13", "manual", "prueba")
    comprobar(not any(f == date(2030, 1, 13) for f, _ in recuperacion.pendientes(ahora)),
              "no se lanza nada para un dia con una ejecucion en curso")
    repositorio.cerrar_ejecucion(en_curso, "cancelada", "", "", {})

    repositorio.guardar_ajuste("recuperacion_desde", "2030-01-16")
    comprobar(all(f >= date(2030, 1, 16) for f, _ in recuperacion.pendientes(ahora)),
              "nada anterior al dia en que se activo la recuperacion")
    repositorio.guardar_ajuste("recuperacion_activa", "0")
    comprobar(recuperacion.pendientes(ahora) == [], "se puede desactivar en Ajustes")
    repositorio.guardar_ajuste("recuperacion_activa", "1")

    repositorio.guardar_ajuste("semanal_ultima_semana", "2030-01-07")
    comprobar(recuperacion.semanal_pendiente(ahora) == date(2030, 1, 14),
              "el resumen semanal del lunes apagado se manda el miercoles")
    repositorio.guardar_ajuste("semanal_ultima_semana", "2030-01-14")
    comprobar(recuperacion.semanal_pendiente(ahora) is None, "y solo una vez por semana")

    comprobar(correo.asunto(FECHA, 2, 1, retraso=True).endswith("(enviado con retraso)")
              and "ENVIADO CON RETRASO" in correo.componer([], FECHA, {"consultados": [],
                                                                       "fallidos": []},
                                                           retraso=True)
              and "ENVIADO CON RETRASO" not in correo.componer([], FECHA, {"consultados": [],
                                                                           "fallidos": []}),
              "el correo recuperado avisa del retraso en el asunto y en el cuerpo")

    # De punta a punta, con el reloj real: hoy a las 00:00 ya paso y no se vigilo.
    hoy = date.today()
    repositorio.guardar_ajuste("hora_ejecucion", "00:00")
    repositorio.guardar_ajuste("tarde_activa", "0")
    repositorio.guardar_ajuste("recuperacion_desde", hoy.isoformat())
    repositorio.guardar_ajuste("semanal_ultima_semana", "2999-01-01")
    if _dt.now(madrid) - _dt.combine(hoy, _dt.min.time(), madrid) > recuperacion.MARGEN:
        antes = [f for f in repositorio.ejecuciones_de_fecha(hoy.isoformat())]
        if not any(recuperacion._buena(f) for f in antes):
            comprobar(recuperacion.recuperar(comprobar_red=lambda: False) == []
                      and len(repositorio.ejecuciones_de_fecha(hoy.isoformat())) == len(antes),
                      "sin conexion no se lanza nada (se reintenta a los 10 minutos)")
            _guion["publicaciones"] = []
            ENVIADOS.clear()
            hecho = recuperacion.recuperar(comprobar_red=lambda: True)
            _esperar_fin()
            tipos = [f["tipo"] for f in repositorio.ejecuciones_de_fecha(hoy.isoformat())]
            comprobar(hecho == [f"recuperada {hoy.isoformat()}"] and "recuperada" in tipos,
                      "al encender se vigila el dia que faltaba")
            comprobar(len(ENVIADOS) == 1 and "(enviado con retraso)" in ENVIADOS[0]["asunto"],
                      "y se manda su correo avisando del retraso")
            comprobar(recuperacion.pendientes() == [], "despues ya no queda nada pendiente")

    print("\n23) El BOE sale el primero del correo")
    from negocio.boletines import ORDEN as _orden

    comprobar("BOE" in ADAPTADORES and _orden[0] == "BOE", "el BOE esta registrado y se consulta el primero")
    base = {"titulo": "Convocatoria de prueba", "relevancia": "media", "fecha_publicacion": "2026-09-17",
            "codigo_boletin": "DOGV", "url_oficial": "https://ejemplo", "id": None}
    html = correo.componer([dict(base, comunidad="Andalucia"), dict(base, comunidad="Estatal (BOE)",
                                                                    codigo_boletin="BOE")],
                           FECHA, {"consultados": ["BOE", "DOGV"], "fallidos": []})
    comprobar(0 < html.find("Estatal (BOE)") < html.find("Andalucia"),
              "en el correo va delante de las comunidades")

    print("\n24) Solo llegan las ayudas para empresas, pymes, fundaciones o entidades privadas")
    comprobar(relevancia.destinatario(
        {"destinatario": "publico", "titulo_resumido": "Ayudas a ayuntamientos y empresas para el comercio"},
        {"titulo": "Orden de 1 de septiembre"}) == "privado",
        "si el resumen del modelo nombra a empresas cuenta como privado aunque el modelo dude")
    comprobar(relevancia.destinatario(
        {"destinatario": "publico", "titulo_resumido": "Subvencion a la Comunidad Autonoma de Canarias"},
        {}) == "publico", "'Comunidad Autonoma' no se confunde con 'autonomos'")
    comprobar(relevancia.destinatario(
        {"destinatario": "personas", "titulo_resumido": "Becas para estudiantes de formacion profesional",
         "beneficiarios": "Estudiantes"},
        {"titulo": "Resolucion de la Consejeria de Economia, Empresas y Empleo por la que se convocan becas"})
        == "personas",
        "el organismo que convoca ('Consejeria de ... Empresas ...') ya no cuela la ayuda como privada")
    comprobar(relevancia.destinatario({}, {"titulo": "Ayudas"}) == "no_consta"
              and relevancia.destinatario({"destinatario": "cualquiera"}, {}) == "no_consta",
              "sin dato o con un valor raro queda como 'no consta'")

    def _cruda(ident, titulo):
        return PublicacionCruda(codigo_boletin="DOGV", titulo=titulo, organismo="Conselleria de Prueba",
                                seccion="III", url_oficial=f"https://dogv.gva.es/{ident}",
                                url_pdf="", fecha="2026-09-25", texto=titulo, identificador=ident)

    _guion["publicaciones"] = [
        _cruda("999101", "Convocatoria de becas y ayudas para estudiantes de formacion profesional"),
        _cruda("999102", "Subvenciones a ayuntamientos para la mejora de caminos rurales"),
        _cruda("999103", "Ayudas a ayuntamientos y empresas para la dinamizacion del comercio local"),
        _cruda("999104", "Subvenciones a fundaciones para proyectos de accion social"),
        _cruda("999105", "Convocatoria de subvenciones del programa de igualdad 2026"),
    ]
    llamar_antes = anthropic_cliente.llamar_json
    relevancia.anthropic_cliente.llamar_json = _modelo_simulado  # la seccion 18 lo cambio
    orquestador.lanzar(date(2026, 9, 25), "manual", "prueba", enviar_correo=False)
    _esperar_fin()
    relevancia.anthropic_cliente.llamar_json = llamar_antes
    ultima = repositorio.ejecuciones(1)[0]
    enviables = {f["titulo"]: f["destinatario"]
                 for f in repositorio.publicaciones_de_ejecucion(ultima["id"])}
    comprobar(len(enviables) == 3, f"de 5 ayudas, van al correo 3 ({len(enviables)})")
    comprobar(not any("estudiantes" in t or "caminos" in t for t in enviables),
              "fuera las de estudiantes y las solo para ayuntamientos")
    comprobar(any("fundaciones" in t for t in enviables) and any("comercio" in t for t in enviables),
              "dentro las de fundaciones y las compartidas con empresas")
    comprobar(sorted(enviables.values()) == ["no_consta", "privado", "privado"],
              "la que no dice a quien va se envia como 'no consta'")
    visibles = [f["titulo"] for f in repositorio.publicaciones({}, limite=1000)]
    comprobar(not any("estudiantes de formacion" in t or "caminos rurales" in t for t in visibles),
              "las descartadas no aparecen en el panel")
    comprobar(repositorio.existe_hash(deduplicador.calcular_hash(
        "DOGV", "Convocatoria de becas y ayudas para estudiantes de formacion profesional")),
        "pero quedan registradas para no volver a pagar al modelo por ellas")
    html = correo.componer([dict(f) for f in repositorio.publicaciones_de_ejecucion(ultima["id"])],
                           date(2026, 9, 25), {"consultados": ["DOGV"], "fallidos": []})
    comprobar(html.count("DESTINATARIO SIN CONFIRMAR") == 1,
              "en el correo, la de destinatario dudoso lleva su aviso")

    print("\n25) El filtro previo aparta sin coste lo que nunca es una ayuda")
    from negocio import prefiltro

    nunca = [
        ("ORDEN EYH/914/2026 por la que se anuncia convocatoria publica para cubrir, mediante el "
         "sistema de libre designacion, el puesto de Jefe de Servicio", "empleo publico"),
        ("Resolucio de convocatoria del concurs especific de merits per proveir el lloc de cap",
         "empleo publico"),
        ("Anuncio de modificacion de los miembros de la Mesa de Contratacion", "contratacion publica"),
        ("Notificaciones. Notificacion de resolucion del procedimiento de acreditacion de "
         "competencias profesionales", "tramite sin convocatoria"),
        ("ANUNCIO por el que se somete a informacion publica la solicitud de autorizacion "
         "administrativa de una instalacion fotovoltaica", "tramite sin convocatoria"),
    ]
    comprobar(all(prefiltro.motivo_ruido(t) == familia for t, familia in nunca),
              "aparta puestos de trabajo, licitaciones y tramites")

    ayudas = [
        "Extracto de la Orden por la que se convocan subvenciones para la contratacion de personal investigador",
        "Ayudas a la provision de puestos de trabajo en empresas de insercion",
        "Bases reguladoras de las ayudas para la proteccion de los animales de compania",
        "Convocatoria del XIX Premio de Cartografia y Territorio",
        "Resolucion por la que se convocan ayudas al asesoramiento para jovenes agricultores",
    ]
    comprobar(all(prefiltro.motivo_ruido(t) is None for t in ayudas),
              "y nunca aparta un titulo que nombre una ayuda, aunque hable de puestos o contratos")

    PETICIONES_DOC.clear()
    LLAMADAS["n"] = 0
    _guion["publicaciones"] = [
        PublicacionCruda(codigo_boletin="DOGV", titulo=nunca[0][0], organismo="Conselleria",
                         seccion="II", url_oficial="https://dogv.gva.es/x1", url_pdf="",
                         fecha="2026-09-26", texto=nunca[0][0], identificador="999201"),
        PublicacionCruda(codigo_boletin="DOGV", titulo=ayudas[0], organismo="Conselleria",
                         seccion="III", url_oficial="https://dogv.gva.es/x2", url_pdf="",
                         fecha="2026-09-26", texto=ayudas[0], identificador="999202"),
    ]
    llamar_antes_pre = anthropic_cliente.llamar_json
    relevancia.anthropic_cliente.llamar_json = _modelo_simulado
    orquestador.lanzar(date(2026, 9, 26), "manual", "prueba", enviar_correo=False)
    _esperar_fin()
    relevancia.anthropic_cliente.llamar_json = llamar_antes_pre
    ultima_pre = repositorio.ejecuciones(1)[0]
    comprobar(ultima_pre["publicaciones_brutas"] == 2 and ultima_pre["candidatas"] == 1,
              f"de 2 publicaciones solo 1 llega al modelo (llegaron {ultima_pre['candidatas']})")
    comprobar("Apartadas sin coste 1" in (ultima_pre["registro"] or ""),
              "y queda anotado en el registro de la ejecucion")

    print("\n26) Las ayudas de financiacion llevan su propia estructura")
    datos_fin = {
        "nombre_ayuda": "Linea de financiacion bonificada 2026", "tipo_ayuda": "financiacion",
        "beneficiarios": "Pymes afectadas por el entorno arancelario",
        "actuaciones": ["Proyectos de inversion", "Capital circulante"],
        "gastos_elegibles": ["Maquinaria", "Software"],
        "inversion_min": "50.000 €", "inversion_max": "1.500.000 €",
        "financiacion": {"inicio_proyecto": "Hasta 12 meses antes de la solicitud",
                         "financiacion_max": "80% en inversion y 100% en circulante",
                         "intereses": "Euribor a un ano + 0,50-0,75%",
                         "amortizacion": "Entre 5 y 10 anos", "carencia": "Hasta 2 anos",
                         "tramo_no_reembolsable": "30%, maximo 200.000 € (minimis)",
                         "garantias": "Segun calificacion economico-financiera",
                         "comision_apertura": "0,5%"},
    }
    publicacion_fin = {"id": 9001, "codigo_boletin": "BOE", "titulo_resumido": "Financiacion"}
    corto_fin = documentos.renderizar("corto", datos_fin, publicacion_fin)
    rotulos = ("Inversión mínima", "Inversión máxima", "Inicio del proyecto", "Financiación máxima",
               "Intereses", "Amortización", "Carencia", "Tramo no reembolsable (TNR)", "Garantías",
               "Comisión de apertura")
    comprobar("Condiciones de financiación:" in corto_fin and all(r in corto_fin for r in rotulos),
              "el resumen corto cambia el apartado de cuantia por las 10 condiciones")
    comprobar("Euribor a un ano + 0,50-0,75%" in corto_fin and "Hasta 2 anos" in corto_fin,
              "con los datos extraidos de la convocatoria")
    comprobar("Tipo de Ayuda y Cuantía" not in corto_fin
              and "plazo en que las actuaciones" not in corto_fin,
              "y sin el apartado de cuantia ni la frase de ejecucion")
    ampliado_fin = documentos.renderizar("ampliado", datos_fin, publicacion_fin)
    comprobar("Condiciones de financiación:" in ampliado_fin
              and "Criterios de valoración:" in ampliado_fin
              and "Documentación de justificación:" in ampliado_fin,
              "el ampliado mantiene sus apartados y solo cambia ese bloque")
    comprobar("Régimen:" in ampliado_fin and "Incompatibilidades:" in ampliado_fin,
              "conservando regimen, compatibilidades e incompatibilidades")

    datos_general = dict(datos_fin, tipo_ayuda="general", cuantia_max="50.000 €", intensidad="40%")
    corto_general = documentos.renderizar("corto", datos_general, publicacion_fin)
    comprobar("Tipo de Ayuda y Cuantía" in corto_general
              and "Condiciones de financiación" not in corto_general,
              "las demas ayudas siguen con la estructura de siempre")
    info_fin = documentos.renderizar("infografia", datos_fin, publicacion_fin)
    comprobar("Condiciones de financiación" in info_fin and "Inversión máxima" in info_fin
              and "Financiación máxima" in info_fin,
              "la infografia de financiacion lleva sus cifras y el bloque de condiciones")
    comprobar("Ayuda máxima" not in info_fin and "Intensidad" not in info_fin,
              "y ya no muestra ayuda maxima ni intensidad, que aqui no aplican")

    sin_tipo = documentos.renderizar("corto", {"nombre_ayuda": "Sin tipo"}, publicacion_fin)
    comprobar("Tipo de Ayuda y Cuantía" in sin_tipo,
              "un documento antiguo, sin tipo de ayuda, se trata como general")
    faltan = documentos.renderizar("corto", {"tipo_ayuda": "financiacion"}, publicacion_fin)
    comprobar(faltan.count(documentos.NO_DISPONIBLE) >= 10,
              "las condiciones que no figuran en la convocatoria llevan su aviso")

    print("\n27) Las ayudas de empleo llevan su propia estructura")
    datos_emp = {
        "nombre_ayuda": "Ayuda a la contratacion indefinida de jovenes cualificados 2026",
        "tipo_ayuda": "empleo",
        "beneficiarios": "Empresas privadas y autonomos",
        "exclusiones": ["Contratos fijos discontinuos", "Contrato a tiempo parcial"],
        "empleo": {
            "personas_destinatarias": "Jovenes menores de 30 anos desempleados con FP o titulacion",
            "requisitos_contratacion": ["Incremento neto de la plantilla media, a mantener dos anos",
                                        "Maximo 2 contrataciones por entidad"],
            "requisitos_trabajadores": ["Inscritos en Garantia Juvenil", "Inscritos en LABORA"],
            "obligaciones_empresario": ["Mantener el empleo creado durante 2 anos"],
            "condiciones_contrato": ["Indefinido a jornada completa", "Duracion de 2 anos"],
            "cuantias": [{"colectivo": "Hombres", "importe": "10.000 €"},
                         {"colectivo": "Mujeres", "importe": "12.500 €"}]},
    }
    publicacion_emp = {"id": 9002, "codigo_boletin": "DOGV", "titulo_resumido": "Empleo"}
    corto_emp = documentos.renderizar("corto", datos_emp, publicacion_emp)
    apartados = ("Personas Destinatarias:", "Beneficiarios:", "Requisitos de la Contratación:",
                 "Requisitos de los trabajadores:", "Exclusiones:", "Obligaciones del Empresario:",
                 "Tipo de Contrato y Cuantía:", "Plazo:")
    comprobar(all(a in corto_emp for a in apartados),
              "el resumen corto trae los ocho apartados del modelo de empleo")
    comprobar(corto_emp.index("Personas Destinatarias:") < corto_emp.index("Beneficiarios:")
              < corto_emp.index("Requisitos de la Contratación:")
              < corto_emp.index("Obligaciones del Empresario:") < corto_emp.index("Plazo:"),
              "y en el mismo orden")
    comprobar("Actuaciones Apoyables" not in corto_emp and "Costes Apoyables" not in corto_emp
              and "Tipo de Ayuda y Cuantía" not in corto_emp,
              "sin los apartados que en empleo no aplican")
    comprobar("Hombres:" in corto_emp and "10.000 €" in corto_emp and "Mujeres:" in corto_emp,
              "con la cuantia de cada colectivo")

    ampliado_emp = documentos.renderizar("ampliado", datos_emp, publicacion_emp)
    comprobar(all(a in ampliado_emp for a in ("Personas Destinatarias:", "Obligaciones del Empresario:",
                                              "Tipo de Contrato y Cuantía:", "Criterios de valoración:",
                                              "Documentación de justificación:", "Crédito presupuestario:")),
              "el ampliado suma sus apartados de siempre a los de empleo")

    info_emp = documentos.renderizar("infografia", datos_emp, publicacion_emp)
    comprobar(all(t in info_emp for t in ("Ayuda por contrato", "Contrato", "Fin de plazo",
                                          "Personas destinatarias", "Requisitos de la contratación",
                                          "Cuantía por colectivo")),
              "la infografia de empleo cambia sus cifras y sus apartados")
    comprobar("10.000 € – 12.500 €" in info_emp,
              "la cifra destacada es el rango de cuantias por colectivo")
    comprobar("Objeto y acciones subvencionables" not in info_emp,
              "sin el apartado de acciones subvencionables")

    info_general = documentos.renderizar("infografia", dict(datos_emp, tipo_ayuda="general"),
                                         publicacion_emp)
    comprobar("Ayuda máxima" in info_general and "Objeto y acciones subvencionables" in info_general
              and "Cuantía por colectivo" not in info_general,
              "la infografia de las ayudas generales no cambia")

    comprobar("Personas Destinatarias" not in documentos.renderizar(
        "corto", dict(datos_emp, tipo_ayuda="general"), publicacion_emp),
        "una ayuda general no usa la estructura de empleo")
    vacia = documentos.renderizar("corto", {"tipo_ayuda": "empleo"}, publicacion_emp)
    comprobar(documentos.NO_DISPONIBLE in vacia and "Personas Destinatarias:" in vacia,
              "si la convocatoria no da esos datos, el apartado sale con su aviso")
    comprobar('<p class="nd"></p>' not in vacia,
              "y ningun apartado se queda con el aviso en blanco")
    import re as _re
    info_vacia = documentos.renderizar("infografia", {"tipo_ayuda": "financiacion"}, publicacion_emp)
    cifras = _re.findall(r'class="val">([^<]*)', info_vacia)
    comprobar(len(cifras) == 3 and all(c == "Sin especificar" for c in cifras),
              f"las cifras destacadas sin dato se resumen, que la frase larga no cabe ({cifras})")
    comprobar(documentos.NO_DISPONIBLE in info_vacia,
              "y el aviso completo sigue en los apartados de abajo")

    aplicacion_mova_planificador = web.config.get("planificador")
    if aplicacion_mova_planificador:
        aplicacion_mova_planificador.shutdown(wait=False)

    print(f"\n{'TODAS LAS COMPROBACIONES PASAN' if not fallos else 'FALLOS: ' + str(fallos)}")
    print(f"Llamadas simuladas al modelo: {LLAMADAS['n']}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
