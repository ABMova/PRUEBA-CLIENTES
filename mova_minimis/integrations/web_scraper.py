"""Acceso a la Base de Datos Nacional de Subvenciones (BDNS / SNPSAP).

No es una simulación: usa la API pública que alimenta el portal
https://www.infosubvenciones.es (sin clave, JSON). Comprobado el 13/10/2026:

  GET {API}/terceros?ambito=M&busqueda=<CIF o nombre>
      -> {"terceros": [{"id": 5557985, "descripcion": "A46103834 - MERCADONA SA"}, ...]}
  GET {API}/minimis/busqueda?page=0&pageSize=N&beneficiario=<id>
      -> página Spring: content[], totalElements. Cada concesión trae
         codigoConcesion, fechaConcesion (AAAA-MM-DD), fechaRegistro, convocante,
         reglamento ("REG (UE) 2023/2831 de minimis, General"...), instrumento,
         numeroConvocatoria, ayudaEquivalente (euros).
  GET {API}/convocatorias?numConv=<n>  -> ficha de la convocatoria (título).

Trampas conocidas: los filtros van en plural o con el nombre exacto del portal
(si no, se ignoran en silencio y devuelven todo); las fechas en dd/mm/aaaa.
La respuesta trae un aviso legal de reutilización ('advertencia') que se
reproduce en los informes.

Si la API cambia, solo hay que tocar este módulo: el resto de la cadena usa
buscar_beneficiarios(), concesiones_minimis() y ficha_convocatoria().
"""
import time

import requests

import config

AVISO_REUTILIZACION = (
    "Datos del Sistema Nacional de Publicidad de Subvenciones y Ayudas Públicas (BDNS). "
    "Su reutilización está sujeta al aviso legal de infosubvenciones.es y la información es dinámica: "
    "puede corregirse o completarse después de la consulta."
)

_sesion = requests.Session()
_sesion.headers.update({"Accept": "application/json", "User-Agent": f"MOVA-Minimis/{config.VERSION}"})


class ErrorBDNS(Exception):
    """La BDNS no respondió o respondió algo inesperado tras los reintentos."""


def _get(ruta: str, params: dict, cancelado=None) -> dict | list:
    url = f"{config.BDNS_API}/{ruta}"
    ultimo = None
    for intento, espera in enumerate((1, 2, 4, None)):
        if cancelado and cancelado():
            raise ErrorBDNS("Cancelado por el usuario")
        try:
            r = _sesion.get(url, params=params, timeout=config.BDNS_TIMEOUT_S)
            if r.status_code == 429 or r.status_code >= 500:
                ultimo = f"HTTP {r.status_code}"
            elif r.status_code >= 400:
                raise ErrorBDNS(f"La BDNS rechazó la petición ({r.status_code}) en {ruta}")
            else:
                return r.json()
        except requests.Timeout:
            ultimo = f"sin respuesta en {config.BDNS_TIMEOUT_S} s"
        except requests.ConnectionError as e:
            ultimo = f"sin conexión ({e.__class__.__name__})"
        except ValueError:
            ultimo = "respuesta que no es JSON"
        if espera is None:
            break
        time.sleep(espera)
    raise ErrorBDNS(f"La BDNS no responde ({ultimo}) tras 4 intentos")


def buscar_beneficiarios(texto: str, cancelado=None) -> list[dict]:
    """Devuelve [{id, cif, nombre}] únicos por id, tal como los tiene registrados la BDNS."""
    datos = _get("terceros", {"ambito": "M", "busqueda": texto}, cancelado)
    vistos: dict[int, dict] = {}
    for t in (datos or {}).get("terceros", []) if isinstance(datos, dict) else []:
        desc = (t.get("descripcion") or "").strip()
        cif, _, nombre = desc.partition(" - ")
        tid = t.get("id")
        if tid is None:
            continue
        ficha = vistos.setdefault(tid, {"id": tid, "cif": cif.strip().upper(), "nombre": nombre.strip(),
                                        "variantes": []})
        if nombre.strip() and nombre.strip() not in ficha["variantes"]:
            ficha["variantes"].append(nombre.strip())
    return list(vistos.values())


def concesiones_minimis(id_beneficiario: int, cancelado=None) -> list[dict]:
    """Todas las concesiones de minimis registradas para un beneficiario (todas las páginas)."""
    resultado, pagina = [], 0
    while True:
        datos = _get("minimis/busqueda", {"page": pagina, "pageSize": 500, "beneficiario": id_beneficiario},
                     cancelado)
        contenido = datos.get("content", []) if isinstance(datos, dict) else []
        resultado.extend(contenido)
        if not contenido or datos.get("last", True) or pagina >= 20:
            return resultado
        pagina += 1


def ficha_convocatoria(numero: str, cancelado=None) -> dict:
    """Título y bases reguladoras (suele ser el BOE o el diario autonómico) de una convocatoria."""
    datos = _get("convocatorias", {"numConv": numero}, cancelado)
    if not isinstance(datos, dict):
        return {}
    return {
        "titulo": (datos.get("descripcion") or datos.get("descripcionLeng") or "").strip() or None,
        "url_bases": datos.get("urlBasesReguladoras") or None,
        "fecha_recepcion": datos.get("fechaRecepcion"),
    }


def url_convocatoria(numero: str | None) -> str | None:
    return f"{config.BDNS_WEB}/convocatorias/{numero}" if numero else None


def url_beneficiario(id_beneficiario: int | None) -> str | None:
    return f"{config.BDNS_WEB}/concesiones/minimis/{id_beneficiario}" if id_beneficiario else None
