"""Configuración general y rutas de MOVA Minimis.

Dos raíces distintas:
- RAIZ_CODIGO: plantillas, estáticos y esquema. Dentro del .exe es sys._MEIPASS.
- DATOS: base de datos, documentos, informes, registros y copias. Nunca dentro
  del .exe ni de una carpeta sincronizada (SQLite se corrompe en OneDrive), por
  eso por defecto va a %LOCALAPPDATA%\\MOVA Minimis.
"""
import os
import sys
from pathlib import Path

VERSION = "1.1.3"
NOMBRE_APP = "MOVA Minimis"

CONGELADO = getattr(sys, "frozen", False)
RAIZ_CODIGO = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# Carpeta del ejecutable (o del proyecto en desarrollo): aquí se busca el .env
CARPETA_EXE = Path(sys.executable).resolve().parent if CONGELADO else Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(CARPETA_EXE / ".env")
except ImportError:  # el .env es opcional
    pass


def _carpeta_datos() -> Path:
    explicita = os.environ.get("MOVA_MINIMIS_DATOS", "").strip()
    if explicita:
        return Path(explicita).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "MOVA Minimis" / ("data" if CONGELADO else "data-dev")


DATOS = _carpeta_datos()
DB_PATH = Path(os.environ.get("DB_PATH") or DATOS / "minimis.db")
DIR_DOCUMENTOS = DATOS / "documentos"
DIR_INFORMES = DATOS / "informes"
DIR_LOGS = DATOS / "logs"
DIR_BACKUPS = DATOS / "backups"
DIR_TEMPORAL = DATOS / "tmp"
FICHERO_CLAVE_CIFRADO = DATOS / "cipher.key"

# Modo escritorio: lo arranca la ventana Electron. Sin inicio de sesión (un solo usuario, el de Windows);
# la administración se protege con una contraseña de configuración. Cada petición debe traer el
# token que la ventana genera al arrancar, para que nada más del equipo pueda usar el puerto.
ESCRITORIO = os.environ.get("MOVA_MODO_ESCRITORIO", "0") == "1"
TOKEN_ESCRITORIO = os.environ.get("MOVA_TOKEN", "")
PID_PADRE = int(os.environ.get("MOVA_PID_PADRE", "0") or 0)
MINUTOS_DESBLOQUEO = 30
# Contraseña de configuración de serie (la pidió así el usuario). Solo su huella PBKDF2: la contraseña
# no está escrita ni en el código ni en el instalador. Se cambia desde Configuración y entonces manda
# el ajuste 'clave_configuracion' de la base.
CLAVE_CONFIG_DEFECTO = "pbkdf2_sha256$390000$WpvJ96VpzA0n31H6KfDXTQ==$8RCCbgcUoLOMLCw9WeSVIX2fUBvO7AihGU4+YTJpV5o="
EMAIL_ESCRITORIO = "equipo@local"

HOST = os.environ.get("MOVA_HOST", "127.0.0.1")
PUERTO = int(os.environ.get("MOVA_PUERTO", "5000"))
ABRIR_NAVEGADOR = os.environ.get("MOVA_ABRIR_NAVEGADOR", "1") == "1"
DETRAS_DE_PROXY = os.environ.get("MOVA_DETRAS_DE_PROXY", "0") == "1"

# Sesión
HORAS_SESION = 8
COPIAS_A_CONSERVAR = 10
MAX_SUBIDA_MB = 25

# Usuario inicial (contraseña provisional, cambio obligatorio en el primer acceso)
ADMIN_INICIAL_EMAIL = "admin@local"
ADMIN_INICIAL_CLAVE = "TemporalAdmin123"

# Modelos de Claude que se pueden elegir desde Configuración
MODELOS_CLAUDE = {
    "claude-haiku-5-5": "Claude Haiku 5.5 (económico)",  # solo el económico, a petición del usuario
}
MODELO_POR_DEFECTO = "claude-haiku-5-5"

# Base de Datos Nacional de Subvenciones (SNPSAP). API pública sin clave.
BDNS_API = os.environ.get("BDNS_API", "https://www.infosubvenciones.es/bdnstrans/api")
BDNS_WEB = "https://www.infosubvenciones.es/bdnstrans/GE/es"
BDNS_TIMEOUT_S = 20
AVISO_BDNS = (
    "Datos del Sistema Nacional de Publicidad de Subvenciones y Ayudas Públicas (BDNS). "
    "Su reutilización está sujeta al aviso legal de infosubvenciones.es y la información es dinámica: "
    "puede corregirse o completarse después de la consulta."
)


def preparar_carpetas() -> None:
    for d in (DATOS, DIR_DOCUMENTOS, DIR_INFORMES, DIR_LOGS, DIR_BACKUPS, DIR_TEMPORAL):
        d.mkdir(parents=True, exist_ok=True)
