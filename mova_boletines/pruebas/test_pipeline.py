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
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

TEMPORAL = Path(tempfile.mkdtemp(prefix="mova-pipeline-"))
os.environ["MOVA_DATOS"] = str(TEMPORAL)
os.environ["MOVA_URL_PUBLICA"] = "http://boletines.interno:8770"

import config  # noqa: E402
from datos import repositorio  # noqa: E402
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


# -------------------------------------------------------- modelo simulado --
LLAMADAS = {"n": 0}


def _modelo_simulado(sistema: str, mensaje: str, modelo: str, max_tokens: int) -> dict:
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
        if es_pyme:
            return {"es_convocatoria_ayuda": True, "titulo": titulo,
                    "resumen": "Subvenciones para modernizacion e inversion productiva de pymes "
                               "industriales de la Comunitat Valenciana.",
                    "organismo_convocante": "Conselleria de Innovacion, Industria, Comercio y Turismo",
                    "plazo_solicitud": "Del 1 al 30 de octubre de 2026",
                    "beneficiarios": "Pymes industriales con centro de trabajo en la Comunitat Valenciana",
                    "importe": "12.000.000 euros",
                    "confianza": "alta", "motivo_confianza": "Todos los datos figuran en el texto."}
        return {"es_convocatoria_ayuda": True, "titulo": titulo,
                "resumen": "Ayudas a asociaciones vecinales para actividades culturales.",
                "organismo_convocante": "Conselleria de Participacion",
                "plazo_solicitud": config.MARCADOR_PENDIENTE,
                "beneficiarios": "Asociaciones vecinales sin animo de lucro",
                "importe": "150.000 euros",
                "confianza": "media", "motivo_confianza": "El plazo no aparece en el texto."}

    # Fase 4 - relevancia
    if es_pyme:
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
    def _modelo_malo(sistema, mensaje, modelo, max_tokens):
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

    print(f"\n{'TODAS LAS COMPROBACIONES PASAN' if not fallos else 'FALLOS: ' + str(fallos)}")
    print(f"Llamadas simuladas al modelo: {LLAMADAS['n']}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
