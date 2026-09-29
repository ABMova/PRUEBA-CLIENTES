"""API de solo lectura para el CRM de MOVA.

El CRM llama aqui con su clave (cabecera X-Clave-CRM) y el token que viajaba en
el boton del correo. Devuelve la ayuda en JSON y, si hacen falta, los PDF de los
resumenes para adjuntarlos al programa.

No hay ninguna ruta de escritura: lo peor que puede hacer quien robe la clave es
leer una ayuda que ya esta publicada en un boletin oficial.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from datos import repositorio
from negocio import crm, documentos
from web import auth

registro = logging.getLogger(__name__)

api_crm = Blueprint("api_crm", __name__, url_prefix="/api/crm")

# Freno por IP: el CRM hace unas pocas llamadas por ayuda, no cientos.
VENTANA_INTENTOS = 15  # minutos
INTENTOS_MAX = 300
RECURSO = "api_crm"

# Lo que el CRM puede marcar como hecho.
ACCIONES = ("programa", "tarea")


def _rechazo(mensaje: str, codigo: int):
    return jsonify({"error": mensaje}), codigo


def _comprobar_clave():
    """None si la llamada es legitima, o la respuesta de rechazo."""
    ip = auth.ip_peticion()
    repositorio.registrar_intento_ip(ip, RECURSO)
    if repositorio.intentos_recientes(ip, VENTANA_INTENTOS, RECURSO) > INTENTOS_MAX:
        return _rechazo("Demasiadas peticiones", 429)
    if not crm.activo():
        return _rechazo("La conexion con el CRM no esta activada", 503)
    if not crm.clave_valida(request.headers.get(crm.CABECERA_CLAVE)):
        repositorio.registrar_auditoria("crm", "api_crm", request.path, "Clave incorrecta",
                                        ip, "error")
        return _rechazo("Clave incorrecta", 401)
    return None


def _publicacion(token: str):
    """(fila, None) si el token vale; (None, respuesta) si no."""
    clave = repositorio.token_documento(token)
    vigente = (clave is not None
               and clave["caduca_en"] > datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    fila = repositorio.publicacion(clave["publicacion_id"]) if vigente else None
    if fila is None:
        return None, _rechazo("Enlace no valido o caducado", 404)
    return fila, None


@api_crm.route("/salud")
def salud():
    """Para que el CRM compruebe la clave sin necesidad de una ayuda concreta."""
    error = _comprobar_clave()
    if error:
        return error
    return jsonify({"estado": "ok", "herramienta": "MOVA Boletines Oficiales"})


@api_crm.route("/publicacion/<token>")
def publicacion(token: str):
    error = _comprobar_clave()
    if error:
        return error
    fila, error = _publicacion(token)
    if error:
        return error
    repositorio.registrar_auditoria("crm", "api_crm", str(fila["id"]),
                                    "Ficha entregada al CRM", auth.ip_peticion())
    return jsonify(crm.ficha(fila))


@api_crm.route("/publicacion/<token>/hecho", methods=["POST"])
def hecho(token: str):
    """El CRM avisa de que ya ha dado de alta el programa o la tarea de esta ayuda.

    Es la unica escritura de toda la API, y solo escribe eso: quien hizo que y
    cuando, para que el correo y el panel lo enseñen. No toca la publicacion.
    """
    error = _comprobar_clave()
    if error:
        return error
    fila, error = _publicacion(token)
    if error:
        return error

    datos = request.get_json(silent=True) or {}
    accion = str(datos.get("accion") or "").strip().lower()
    if accion not in ACCIONES:
        return _rechazo("Accion desconocida", 400)
    usuario = str(datos.get("usuario") or "")[:120]
    detalle = str(datos.get("detalle") or "")[:500]

    repositorio.registrar_crm(fila["id"], accion, usuario, detalle)
    repositorio.registrar_auditoria("crm", "api_crm", str(fila["id"]),
                                    f"{accion} por {usuario or 'sin identificar'}",
                                    auth.ip_peticion())
    registro.info("El CRM ha dado de alta %s de la publicacion %s (%s)", accion, fila["id"], usuario)
    return jsonify({"estado": "ok"})


@api_crm.route("/publicacion/<token>/documento/<tipo>")
def documento(token: str, tipo: str):
    """PDF del resumen. 202 mientras se genera: el CRM vuelve a preguntar."""
    error = _comprobar_clave()
    if error:
        return error
    if tipo not in documentos.TIPOS:
        return _rechazo("Tipo de documento desconocido", 404)
    fila, error = _publicacion(token)
    if error:
        return error

    doc = repositorio.documento(fila["id"])
    if doc is None or doc["estado"] != "listo":
        if documentos.generando(fila["id"]):
            return jsonify({"estado": "generando"}), 202
        aceptada, mensaje = documentos.lanzar(fila["id"], "CRM")
        if not aceptada:
            registro.warning("Documento %s no lanzado para el CRM: %s", fila["id"], mensaje)
            return jsonify({"estado": "error", "detalle": mensaje}), 503
        return jsonify({"estado": "generando"}), 202

    contenido, mime, nombre = documentos.descarga(
        tipo, json.loads(doc["datos_json"] or "{}"), dict(fila))
    respuesta = Response(contenido, mimetype=mime)
    respuesta.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta
