"""Lo que se abre desde el correo, sin iniciar sesion.

Los botones del correo diario (los tres resumenes, la lista de seguimiento, la
marca del CRM y el descarte) llevan una clave propia de cada publicacion. Esa
clave no da acceso a nada mas de la herramienta: ni al panel, ni a los ajustes,
ni a otras publicaciones. Por eso viven aparte de web/rutas.py, que es la parte
con sesion.

Todas estas rutas estan en RUTAS_PUBLICAS (app.py), que es lo unico que responde
cuando la peticion llega desde internet.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from flask import Blueprint, Response, redirect, render_template, jsonify, url_for

from datos import repositorio
from negocio import crm, documentos, insignia
from web import auth

registro = logging.getLogger(__name__)

publico = Blueprint("publico", __name__)

# Freno por IP, comun a los enlaces del correo.
INTENTOS_MAX_IP = 20
VENTANA_INTENTOS = 10  # minutos


def respuesta_descarga(tipo: str, doc, fila) -> Response:
    contenido, mime, nombre = documentos.descarga(
        tipo, json.loads(doc["datos_json"] or "{}"), dict(fila))
    return Response(contenido, mimetype=mime,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# --------------------- botones del correo: acceso con clave, sin iniciar sesion --
# Quien recibe el correo puede generar y ver los tres documentos de ESA
# publicacion. La clave no da acceso a nada mas de la herramienta, no permite
# regenerar (la IA se paga una vez por publicacion) y caduca a los 90 dias.
INTENTOS_MAX_DOCUMENTO = 200  # aperturas de enlaces del correo, por IP y ventana
# La pagina de espera pregunta "ya esta?" cada pocos segundos. Va en su propio
# contador, mucho mas alto: si compartiera el de las aperturas, una oficina que
# sale a internet por una sola IP se bloquearia sola mientras espera documentos.
INTENTOS_MAX_ESPERA = 2000


def _publicacion_por_clave(token: str, tipo: str, contar: bool = True):
    """Devuelve (fila, None) si la clave vale, o (None, respuesta de error).

    contar=False para la consulta de la pagina de espera: no gasta el limite de
    aperturas ni suma un uso al enlace, pero sigue comprobando la clave.
    """
    ip = auth.ip_peticion()
    recurso = "documento" if contar else "documento_espera"
    maximo = INTENTOS_MAX_DOCUMENTO if contar else INTENTOS_MAX_ESPERA
    repositorio.registrar_intento_ip(ip, recurso)
    if repositorio.intentos_recientes(ip, VENTANA_INTENTOS, recurso) > maximo:
        return None, (render_template("descarte_ok.html", titulo_pagina="Documentos",
                                      titulo_resultado="Demasiadas peticiones", clase="error",
                                      mensaje="Espera unos minutos y vuelve a intentarlo.",
                                      publicacion=""), 429)
    clave = repositorio.token_documento(token)
    valida = (clave is not None and tipo in documentos.TIPOS
              and clave["caduca_en"] > datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    fila = repositorio.publicacion(clave["publicacion_id"]) if valida else None
    if fila is None:
        repositorio.registrar_auditoria("anonimo", "documento_clave", token[:12],
                                        "Clave inexistente o caducada", ip, "error")
        return None, (render_template("descarte_ok.html", titulo_pagina="Documentos",
                                      titulo_resultado="Enlace no valido", clase="error",
                                      mensaje="Este enlace no es valido o ha caducado. Pide a "
                                              "alguien de MOVA que te reenvie la publicacion.",
                                      publicacion=""), 404)
    if contar:
        repositorio.usar_token_documento(token, ip)
    return fila, None


@publico.route("/s/<token>/<accion>")
def seguimiento_por_token(token: str, accion: str):
    """Botones Seguimiento y Quitar del seguimiento de los correos.

    Van sin contrasena, como los demas botones del correo: el token identifica
    la publicacion. La lista es del equipo y da igual quien pulse, asi que no se
    guarda el autor.
    """
    if accion not in ("marcar", "quitar"):
        return _pagina_seguimiento("Enlace no valido", "error",
                                   "Este enlace no sirve para nada.", 404)
    ip = auth.ip_peticion()
    repositorio.registrar_intento_ip(ip, "seguimiento")
    if repositorio.intentos_recientes(ip, VENTANA_INTENTOS, "seguimiento") > INTENTOS_MAX_IP:
        return _pagina_seguimiento("Demasiadas peticiones", "error",
                                   "Espera unos minutos y vuelve a intentarlo.", 429)

    clave = repositorio.token_documento(token)
    fila = repositorio.publicacion(clave["publicacion_id"]) if clave else None
    if fila is None:
        return _pagina_seguimiento("Enlace no valido", "error",
                                   "Este enlace no es valido o ha caducado.", 404)

    titulo = fila["titulo_resumido"] or fila["titulo"][:120]
    if accion == "marcar":
        repositorio.marcar_seguimiento(fila["id"])
        repositorio.registrar_auditoria("correo", "seguimiento", str(fila["id"]),
                                        "Marcada para seguimiento", ip)
        return _pagina_seguimiento(
            "Guardada en seguimiento", "ok",
            "La recibiras en el correo de seguimiento de los lunes, miercoles y viernes. "
            "Sale sola de la lista cuando vence su plazo o, si no tiene fecha, a los "
            f"{repositorio.ajuste_int('dias_seguimiento_sin_plazo', 60)} dias.",
            publicacion=titulo)

    quitada = repositorio.quitar_seguimiento(fila["id"])
    repositorio.registrar_auditoria("correo", "seguimiento", str(fila["id"]),
                                    "Quitada del seguimiento" if quitada else "No estaba en la lista",
                                    ip)
    return _pagina_seguimiento(
        "Fuera del seguimiento" if quitada else "No estaba en la lista", "ok",
        "Ya no saldra en el correo de seguimiento." if quitada
        else "Esta publicacion no estaba en la lista de seguimiento.", publicacion=titulo)


def _pagina_seguimiento(titulo: str, clase: str, mensaje: str, codigo: int = 200,
                        publicacion: str = ""):
    pagina = render_template("descarte_ok.html", titulo_pagina="Seguimiento",
                             titulo_resultado=titulo, clase=clase, mensaje=mensaje,
                             publicacion=publicacion)
    return (pagina, codigo) if codigo != 200 else pagina


@publico.route("/crm/estado/<token>.png")
def marca_crm(token: str):
    """La marca verde del correo: dice si esa ayuda ya se llevo al CRM y quien.

    Es lo unico que un correo ya entregado vuelve a pedirle al servidor, asi que
    es la via para que el equipo vea desde la bandeja de entrada lo que ya esta
    hecho. Sin token valido o sin nada hecho, se devuelve un punto invisible: el
    correo no se rompe y no se filtra nada.
    """
    clave = repositorio.token_documento(token)
    filas = repositorio.crm_de_publicacion(clave["publicacion_id"]) if clave else []
    texto = crm.resumen_hecho(filas)
    contenido = insignia.verde(texto) if texto else insignia.transparente()
    respuesta = Response(contenido, mimetype="image/png")
    # Sin esto, Outlook enseñaria siempre la primera imagen que descargo.
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    respuesta.headers["Expires"] = "0"
    return respuesta


@publico.route("/d/<token>/<tipo>")
def documento_por_clave(token: str, tipo: str):
    fila, error = _publicacion_por_clave(token, tipo)
    if error:
        return error

    doc = repositorio.documento(fila["id"])
    if doc is not None and doc["estado"] == "listo":
        barra = {
            "volver": "",
            "url_tipo": {t: url_for("publico.documento_por_clave", token=token, tipo=t)
                         for t in documentos.TIPOS},
            "descargar": url_for("publico.descargar_por_clave", token=token, tipo=tipo),
            "regenerar": "",
            "nota": f"{doc['paginas']} pag. analizadas",
        }
        return documentos.renderizar(tipo, json.loads(doc["datos_json"] or "{}"), dict(fila), barra)

    def estado(nombre: str):
        # Quien viene del correo solo ve "Generando" y luego el documento: ni
        # fases ni mensajes tecnicos (el motivo de un fallo queda en el registro).
        return render_template(
            "documento_espera.html", rotulo=documentos.TIPOS[tipo][0], estado=nombre,
            titulo=fila["titulo_resumido"] or fila["titulo"][:160],
            url_oficial=fila["url_oficial"] or fila["url_pdf"],
            url_listo=url_for("publico.documento_por_clave_listo", token=token, tipo=tipo),
            url_reintentar=url_for("publico.documento_por_clave", token=token, tipo=tipo,
                                   reintentar=1))

    if documentos.generando(fila["id"]):
        return estado("generando")
    if doc is not None and doc["estado"] == "error" and not request.args.get("reintentar"):
        return estado("error")

    aceptada, mensaje = documentos.lanzar(fila["id"], f"correo ({auth.ip_peticion()})")
    if not aceptada:
        registro.warning("Documento de la publicacion %s no lanzado: %s",
                         fila["id"], mensaje)
    return estado("generando") if aceptada else estado("error")


@publico.route("/d/<token>/<tipo>/listo")
def documento_por_clave_listo(token: str, tipo: str):
    """Lo consulta la pagina de espera cada pocos segundos: ya esta, o ha fallado."""
    fila, error = _publicacion_por_clave(token, tipo, contar=False)
    if error:
        return jsonify({"listo": False, "error": True}), 404
    doc = repositorio.documento(fila["id"])
    en_curso = documentos.generando(fila["id"])
    return jsonify({"listo": bool(doc is not None and doc["estado"] == "listo" and not en_curso),
                    "error": bool(doc is not None and doc["estado"] == "error" and not en_curso)})


@publico.route("/d/<token>/<tipo>/descargar")
def descargar_por_clave(token: str, tipo: str):
    fila, error = _publicacion_por_clave(token, tipo)
    if error:
        return error
    doc = repositorio.documento(fila["id"])
    if doc is None or doc["estado"] != "listo":
        return redirect(url_for("publico.documento_por_clave", token=token, tipo=tipo))
    return respuesta_descarga(tipo, doc, fila)


# -------------------------------- ruta publica de descarte (unica sin sesion) --
@publico.route("/descartar/<token>")
def descartar_por_token(token: str):
    ip = auth.ip_peticion()
    repositorio.registrar_intento_ip(ip, "descarte")
    if repositorio.intentos_recientes(ip, VENTANA_INTENTOS, "descarte") > INTENTOS_MAX_IP:
        repositorio.registrar_auditoria("anonimo", "descarte_token", token[:12],
                                        "Demasiados intentos desde la misma IP", ip, "error")
        return render_template("descarte_ok.html", titulo_pagina="Descarte",
                               titulo_resultado="Demasiados intentos", clase="error",
                               mensaje="Se han hecho demasiadas peticiones desde esta direccion. "
                                       "Espera unos minutos.", publicacion=""), 429

    fila = repositorio.token_descarte(token)
    if fila is None:
        repositorio.registrar_auditoria("anonimo", "descarte_token", token[:12],
                                        "Token inexistente", ip, "error")
        return render_template("descarte_ok.html", titulo_pagina="Descarte",
                               titulo_resultado="Enlace no valido", clase="error",
                               mensaje="Este enlace de descarte no es valido.",
                               publicacion=""), 404

    if fila["usado"]:
        return render_template("descarte_ok.html", titulo_pagina="Descarte",
                               titulo_resultado="Enlace ya utilizado", clase="warn",
                               mensaje="Esta publicacion ya se habia descartado con este enlace.",
                               publicacion="")

    if fila["caduca_en"] <= datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        return render_template("descarte_ok.html", titulo_pagina="Descarte",
                               titulo_resultado="Enlace caducado", clase="warn",
                               mensaje="Este enlace ha caducado. Puedes descartar la publicacion "
                                       "desde la herramienta.", publicacion="")

    publicacion = repositorio.publicacion(fila["publicacion_id"])
    repositorio.descartar(fila["publicacion_id"], "correo", destinatario=fila["destinatario"], ip=ip)
    repositorio.consumir_token(token, ip)
    repositorio.registrar_auditoria(fila["destinatario"] or "anonimo", "descarte_token",
                                    str(fila["publicacion_id"]), "Descarte desde el correo", ip)
    return render_template("descarte_ok.html", titulo_pagina="Descarte",
                           titulo_resultado="Publicacion descartada", clase="ok",
                           mensaje="Hecho: no volvera a aparecer en los correos diarios.",
                           publicacion=publicacion["titulo"] if publicacion else "")
