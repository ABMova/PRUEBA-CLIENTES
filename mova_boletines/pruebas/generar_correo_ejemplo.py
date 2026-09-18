"""Prueba 5 - genera el correo de ejemplo y comprueba su contenido.

Escribe _DATOS/correo_ejemplo.html (DATOS/correo_ejemplo.html al ejecutarse
empaquetado) con datos de muestra de tres comunidades, y verifica que salen
las cabeceras por comunidad, la etiqueta de alta relevancia, los enlaces de
descarte y el marcador de dato ausente.

    .venv\\Scripts\\python.exe pruebas\\generar_correo_ejemplo.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import config  # noqa: E402
from datos import repositorio  # noqa: E402
from negocio import correo  # noqa: E402

FECHA = date(2026, 9, 17)
PENDIENTE = config.MARCADOR_PENDIENTE

MUESTRA = [
    {
        "id": 1, "comunidad": "Comunidad Valenciana", "codigo_boletin": "DOGV",
        "boletin_nombre": "Diari Oficial de la Generalitat Valenciana",
        "fecha_publicacion": "2026-09-17",
        "titulo": ("ORDEN 12/2026, de 15 de septiembre, de la Conselleria de Innovacion e "
                   "Industria, por la que se convocan subvenciones para la modernizacion e "
                   "inversion productiva de pymes industriales"),
        "resumen": ("Subvenciones en concurrencia competitiva para modernizar lineas de "
                    "produccion e invertir en equipamiento industrial.\n"
                    "Dirigidas a pymes industriales con centro de trabajo en la Comunitat."),
        "organismo": "Conselleria de Innovacion, Industria, Comercio y Turismo",
        "plazo": "Del 1 al 30 de octubre de 2026",
        "beneficiarios": "Pymes industriales con centro de trabajo en la Comunitat Valenciana",
        "importe": "12.000.000 euros",
        "url_oficial": "https://dogv.gva.es/es/disposicio-canonica?sig=990001",
        "url_pdf": "https://dogv.gva.es/datos/2026/09/17/pdf/2026_99001_es.pdf",
        "relevancia": "alta", "revision_manual": 0,
    },
    {
        "id": 2, "comunidad": "Andalucia", "codigo_boletin": "BOJA",
        "boletin_nombre": "Boletin Oficial de la Junta de Andalucia",
        "fecha_publicacion": "2026-09-17",
        "titulo": ("Orden de 10 de septiembre de 2026, por la que se aprueban las bases "
                   "reguladoras de incentivos a la digitalizacion y la eficiencia energetica "
                   "de la pyme andaluza"),
        "resumen": "Incentivos a la digitalizacion y a la eficiencia energetica de pymes.",
        "organismo": "Consejeria de Industria, Energia y Minas",
        "plazo": PENDIENTE,
        "beneficiarios": "Pymes y personas autonomas con domicilio fiscal en Andalucia",
        "importe": PENDIENTE,
        "url_oficial": "https://www.juntadeandalucia.es/boja/2026/181/1.html",
        "url_pdf": "https://www.juntadeandalucia.es/boja/2026/181/BOJA26-181-00003.pdf",
        "relevancia": "alta", "revision_manual": 1,
    },
    {
        "id": 3, "comunidad": "Castilla y Leon", "codigo_boletin": "BOCYL",
        "boletin_nombre": "Boletin Oficial de Castilla y Leon",
        "fecha_publicacion": "2026-09-17",
        "titulo": ("EXTRACTO de la Orden de 12 de septiembre de 2026, por la que se convocan "
                   "ayudas a entidades locales para actividades de formacion"),
        "resumen": "Ayudas a ayuntamientos para programas de formacion municipal.",
        "organismo": "Consejeria de la Presidencia",
        "plazo": "Un mes desde la publicacion",
        "beneficiarios": "Entidades locales de Castilla y Leon",
        "importe": "400.000 euros",
        "url_oficial": "https://bocyl.jcyl.es/boletines/2026/09/17/html/BOCYL-D-17092026-4.do",
        "url_pdf": "https://bocyl.jcyl.es/boletines/2026/09/17/pdf/BOCYL-D-17092026-4.pdf",
        "relevancia": "media", "revision_manual": 0,
    },
]

fallos: list[str] = []


def comprobar(condicion: bool, mensaje: str) -> None:
    print(f"  {'OK   ' if condicion else 'FALLO'} {mensaje}")
    if not condicion:
        fallos.append(mensaje)


def main() -> int:
    # El correo consulta la URL publica en ajustes, asi que hace falta el esquema.
    repositorio.aplicar_esquema()
    tokens = {1: "tokenEjemplo0000000000000000DOGV",
              2: "tokenEjemplo0000000000000000BOJA",
              3: "tokenEjemplo000000000000000BOCYL"}
    resumen = {
        "consultados": ["DOGV", "BOCM", "DOGC", "BOJA", "DOCM", "BOCYL"],
        "fallidos": [{"codigo": "BORM", "motivo": "reto anti-bot del BORM (Radware)"}],
    }
    html = correo.componer(MUESTRA, FECHA, resumen, tokens)
    destino = correo.guardar_copia(html, "correo_ejemplo.html")

    print(f"Correo de ejemplo: {destino}")
    print(f"Tamano: {destino.stat().st_size} bytes\n")

    texto = destino.read_text(encoding="utf-8")
    comprobar("Comunidad Valenciana" in texto, "cabecera de Comunidad Valenciana")
    comprobar("Andalucia" in texto, "cabecera de Andalucia")
    comprobar("Castilla y Leon" in texto, "cabecera de Castilla y Leon")
    comprobar(texto.count("ALTA RELEVANCIA") == 2, "dos etiquetas de alta relevancia")
    comprobar(config.MARCADOR_REVISION in texto, "etiqueta de revision manual")
    comprobar(texto.count("Descartar esta publicacion") == 3, "tres enlaces de descarte")
    comprobar(all(f"/descartar/{t}" in texto for t in tokens.values()),
              "cada enlace lleva su token")
    comprobar("BORM" in texto and "anti-bot" in texto, "dice que el BORM ha fallado")
    comprobar("Enlace" in texto or "Publicacion oficial" in texto, "enlaces a la publicacion")
    comprobar("PDF" in texto, "enlaces al PDF")
    comprobar("<img" not in texto, "sin imagenes externas")
    comprobar("display:flex" not in texto and "display:grid" not in texto,
              "sin flexbox ni grid (compatible con Outlook)")
    comprobar("<table" in texto, "maquetado con tablas")
    comprobar("#b8892f" in texto, "acento dorado de la paleta MOVA")
    for campo in ("Comunidad", "Boletin", "Fecha publicacion", "Titulo completo", "Organismo",
                  "Enlaces"):
        comprobar(f">{campo}<" in texto, f"campo '{campo}' presente")
    for campo in ("Resumen", "Plazo", "Beneficiarios", "Importe"):
        comprobar(f">{campo}<" not in texto, f"campo '{campo}' retirado")
    for tipo in ("corto", "ampliado", "infografia"):
        comprobar(texto.count(f"/documento/{tipo}") == 3,
                  f"boton '{tipo}' en las tres publicaciones")

    print(f"\n{'TODAS LAS COMPROBACIONES PASAN' if not fallos else 'FALLOS: ' + str(fallos)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
