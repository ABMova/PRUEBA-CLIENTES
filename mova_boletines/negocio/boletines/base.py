"""Contrato comun de los adaptadores de boletin.

Todo adaptador expone:
    CODIGO, NOMBRE, COMUNIDAD, URL_COMPROBADA, FECHA_COMPROBACION
    obtener_publicaciones(fecha: date) -> list[PublicacionCruda]

La capa de negocio no sabe como accede cada boletin: solo pide publicaciones.
Cuando la web de origen cambie, se repara UN adaptador sin tocar nada mas.
"""
from __future__ import annotations

import ssl
import time
from dataclasses import dataclass, field
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

import config


class ErrorBoletin(Exception):
    """Fallo controlado de un adaptador: aisla el boletin, no la ejecucion."""


@dataclass
class PublicacionCruda:
    codigo_boletin: str
    titulo: str
    organismo: str = ""
    seccion: str = ""
    url_oficial: str = ""
    url_pdf: str = ""
    fecha: str = ""          # ISO aaaa-mm-dd
    texto: str = ""          # texto disponible en el sumario
    identificador: str = ""
    extra: dict = field(default_factory=dict)


_CABECERAS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "es-ES,es;q=0.9",
}

# Algunos boletines rechazan agentes no navegador (BORM usa un anti-bot
# comercial). Para ellos se usa una identificacion de navegador, manteniendo
# el contacto en la cabecera From para que el organismo pueda localizarnos.
_CABECERAS_NAVEGADOR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept-Language": "es-ES,es;q=0.9",
    "From": "antonio@mova.es",
}


class _AdaptadorTLSLegado(HTTPAdapter):
    """TLS permisivo para servidores con configuracion antigua.

    El servicio del DOGC (portaldogc.gencat.cat) negocia cifrados que OpenSSL 3
    rechaza por defecto, y la conexion falla con SSLV3_ALERT_HANDSHAKE_FAILURE.
    Se baja el nivel de seguridad SOLO para los boletines que lo necesitan; la
    verificacion del certificado se mantiene activa.
    """

    def init_poolmanager(self, *args, **kwargs):  # noqa: D102
        contexto = create_urllib3_context(ciphers="DEFAULT:@SECLEVEL=1")
        contexto.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        kwargs["ssl_context"] = contexto
        return super().init_poolmanager(*args, **kwargs)


_sesion_legado: requests.Session | None = None


def _sesion(tls_legado: bool) -> requests.Session | requests:
    global _sesion_legado
    if not tls_legado:
        return requests
    if _sesion_legado is None:
        _sesion_legado = requests.Session()
        _sesion_legado.mount("https://", _AdaptadorTLSLegado())
    return _sesion_legado


def pedir(url: str, *, metodo: str = "GET", datos: dict | None = None,
          cabeceras: dict | None = None, navegador: bool = False,
          reintentos: int | None = None, permitir_redirecciones: bool = True,
          tls_legado: bool = False) -> requests.Response:
    """Descarga con reintentos y retroceso exponencial (1s, 2s, 4s)."""
    intentos = reintentos if reintentos is not None else config.REINTENTOS_BOLETIN
    cab = dict(_CABECERAS_NAVEGADOR if navegador else _CABECERAS)
    if cabeceras:
        cab.update(cabeceras)

    cliente = _sesion(tls_legado)
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            respuesta = cliente.request(
                metodo, url, data=datos, headers=cab, timeout=config.TIEMPO_ESPERA,
                allow_redirects=permitir_redirecciones)
            if respuesta.status_code >= 500:
                raise ErrorBoletin(f"HTTP {respuesta.status_code} en {url}")
            respuesta.raise_for_status()
            return respuesta
        except (requests.RequestException, ErrorBoletin) as error:
            ultimo_error = error
            if intento < intentos:
                time.sleep(2 ** (intento - 1))
    raise ErrorBoletin(f"No se pudo descargar tras {intentos} intentos: {ultimo_error}")


def detectar_anti_bot(texto: str) -> bool:
    """Reconoce las paginas de reto anti-bot para no confundirlas con sumarios."""
    marcas = ("Radware Captcha", "validate.perfdrive.com", "made us think that you are a bot",
              "hcaptcha", "Attention Required! | Cloudflare")
    minusculas = texto[:4000].lower()
    return any(marca.lower() in minusculas for marca in marcas)


def iso(fecha: date) -> str:
    return fecha.strftime("%Y-%m-%d")
