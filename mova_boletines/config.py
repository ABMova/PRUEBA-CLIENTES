"""Configuracion central de MOVA Boletines Oficiales.

Resuelve rutas tanto en ejecucion desde codigo como empaquetado con PyInstaller.
Regla: los recursos de solo lectura (plantillas, estaticos, esquema.sql) viven
dentro del paquete (sys._MEIPASS cuando existe); los datos SIEMPRE viven en la
carpeta DATOS junto al ejecutable, nunca en la carpeta temporal.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

NOMBRE_APP = "MOVA Boletines Oficiales"
VERSION = "1.18.0"
LEMA = "Vigilancia diaria de ayudas y subvenciones en boletines autonomicos"


def _empaquetado() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def raiz_recursos() -> Path:
    """Carpeta de recursos de solo lectura (plantillas, estaticos, esquema.sql)."""
    if _empaquetado():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def raiz_ejecutable() -> Path:
    """Carpeta donde vive el ejecutable (o el codigo). Aqui cuelga DATOS/."""
    if _empaquetado():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# El .env se lee de junto al ejecutable; si no esta, del directorio de trabajo.
_env = raiz_ejecutable() / ".env"
load_dotenv(_env if _env.exists() else None)


def _ruta_datos() -> Path:
    """Carpeta de datos: DATOS junto al ejecutable, _DATOS al ejecutar el codigo.

    Windows no distingue mayusculas en los nombres de carpeta, asi que en el
    repositorio DATOS/ y el paquete datos/ serian la MISMA carpeta y los datos
    acabarian mezclados con el codigo. Empaquetado no hay paquete datos/ al
    lado del .exe, asi que ahi si se usa DATOS tal y como se especifico.
    """
    personalizada = os.getenv("MOVA_DATOS", "").strip()
    if personalizada:
        return Path(personalizada).expanduser().resolve()
    if _empaquetado():
        return raiz_ejecutable() / "DATOS"
    return raiz_ejecutable() / "_DATOS"


DATOS = _ruta_datos()
RUTA_BD = DATOS / "mova.db"
RUTA_CLAVE = DATOS / "clave.key"
RUTA_ADJUNTOS = DATOS / "adjuntos"
RUTA_REGISTROS = DATOS / "registros"
RUTA_COPIAS = DATOS / "copias"

RUTA_ESQUEMA = raiz_recursos() / "datos" / "esquema.sql"
RUTA_PLANTILLAS = raiz_recursos() / "web" / "plantillas"
RUTA_ESTATICOS = raiz_recursos() / "web" / "estaticos"

HOST = os.getenv("MOVA_HOST", "127.0.0.1")
PUERTO = int(os.getenv("MOVA_PUERTO", "8770"))
ABRIR_NAVEGADOR = os.getenv("MOVA_ABRIR_NAVEGADOR", "1") == "1"
URL_PUBLICA = os.getenv("MOVA_URL_PUBLICA", f"http://{HOST}:{PUERTO}").rstrip("/")
LOG_NIVEL = os.getenv("MOVA_LOG_NIVEL", "INFO").upper()

# Publicacion en internet. Detras de Nginx (o de un tunel) la IP real del
# visitante llega en X-Forwarded-For; solo se confia en esa cabecera si se
# declara aqui, porque sin proxy cualquiera podria falsificarla y saltarse los
# limites de intentos.
DETRAS_DE_PROXY = os.getenv("MOVA_DETRAS_DE_PROXY", "0") == "1"
# Desde la direccion publica solo se sirven los enlaces del correo (por defecto).
PUBLICO_SOLO_ENLACES = os.getenv("MOVA_PUBLICO_SOLO_ENLACES", "1") == "1"
# Recuperar al encender lo que no se hizo a su hora (las pruebas lo apagan).
RECUPERACION = os.getenv("MOVA_RECUPERACION", "1") == "1"
HTTPS = URL_PUBLICA.lower().startswith("https://")
API_KEY_ENTORNO = os.getenv("ANTHROPIC_API_KEY", "").strip()

ZONA_HORARIA = "Europe/Madrid"
USER_AGENT = f"MOVA-Boletines/{VERSION} (herramienta interna de vigilancia de ayudas; contacto: antonio@mova.es)"
TIEMPO_ESPERA = 30
REINTENTOS_BOLETIN = 3

MARCADOR_PENDIENTE = "[PENDIENTE: dato]"
MARCADOR_REVISION = "[REVISION MANUAL]"

MODELOS_DISPONIBLES = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]

ROLES = ("administrador", "editor", "consulta")


def preparar_carpetas() -> None:
    for carpeta in (DATOS, RUTA_ADJUNTOS, RUTA_REGISTROS, RUTA_COPIAS):
        carpeta.mkdir(parents=True, exist_ok=True)
