"""Rutas web.

Aqui SOLO se valida la entrada, se comprueban permisos y se elige plantilla.
Nada de logica de dominio ni de SQL: eso vive en negocio/ y en datos/.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, current_app, flash, redirect, render_template,
                   request, send_file, url_for)

import config
from datos import copias as copias_datos
from datos import repositorio
from integraciones import anthropic_cliente
from negocio import correo, documentos, orquestador
from negocio.boletines import fichas
from negocio.extraccion import tesseract_disponible
from web import auth

registro = logging.getLogger(__name__)
web = Blueprint("web", __name__)

INTENTOS_MAX_IP = 20
VENTANA_INTENTOS = 10  # minutos


# ------------------------------------------------------------ contexto comun --
@web.app_context_processor
def contexto():
    return {
        "nombre_app": config.NOMBRE_APP,
        "lema": config.LEMA,
        "version": config.VERSION,
        # Fecha hasta la que un fin de plazo se pinta como urgente (rojo).
        "hoy_mas_alerta": (date.today() + timedelta(
            days=repositorio.ajuste_int("dias_alerta", 15))).isoformat(),
        "marcador": config.MARCADOR_PENDIENTE,
        "marcador_revision": config.MARCADOR_REVISION,
        "carpeta_datos": str(config.DATOS),
        "usuario": auth.usuario_actual(),
    }


def _proxima_ejecucion(trabajo_id: str = "vigilancia_diaria") -> str:
    planificador = current_app.config.get("planificador")
    if not planificador:
        return ""
    trabajo = planificador.get_job(trabajo_id)
    if trabajo is None or trabajo.next_run_time is None:
        return ""
    return trabajo.next_run_time.strftime("%d/%m/%Y %H:%M")


def _proximas() -> list[tuple[str, str]]:
    """Todos los disparos programados, para el panel."""
    planificador = current_app.config.get("planificador")
    if not planificador:
        return []
    return [(trabajo.name, trabajo.next_run_time.strftime("%d/%m/%Y %H:%M"))
            for trabajo in sorted(planificador.get_jobs(),
                                  key=lambda t: t.next_run_time or datetime.max)
            if trabajo.next_run_time]


def _cambio() -> float:
    try:
        return float(repositorio.ajuste("cambio_usd_eur", "0.86") or 0.86)
    except ValueError:
        return 0.86


# ------------------------------------------------------------------ acceso --
@web.route("/login", methods=["GET", "POST"])
def login():
    if auth.usuario_actual():
        return redirect(url_for("web.panel"))

    provisional = current_app.config.get("clave_provisional")
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        clave = request.form.get("clave") or ""
        correcto, mensaje = auth.iniciar_sesion(usuario, clave, auth.ip_peticion(),
                                                request.headers.get("User-Agent", ""))
        if correcto:
            destino = request.form.get("siguiente") or url_for("web.panel")
            return redirect(destino if destino.startswith("/") else url_for("web.panel"))
        flash(mensaje, "error")

    return render_template("login.html", titulo_pagina="Acceso",
                           siguiente=request.args.get("siguiente", ""),
                           clave_provisional=provisional)


@web.route("/salir")
def salir():
    auth.cerrar_sesion(auth.ip_peticion())
    flash("Sesion cerrada", "ok")
    return redirect(url_for("web.login"))


@web.route("/cambiar-clave", methods=["GET", "POST"])
def cambiar_clave():
    fila = auth.usuario_actual()
    if fila is None:
        return redirect(url_for("web.login"))

    if request.method == "POST":
        actual = request.form.get("actual") or ""
        nueva = request.form.get("nueva") or ""
        repetida = request.form.get("repetida") or ""
        usuario = repositorio.usuario_por_id(fila["usuario_id"])

        if not repositorio.verificar_clave(usuario, actual):
            flash("La contrasena actual no es correcta", "error")
        elif nueva != repetida:
            flash("Las dos contrasenas nuevas no coinciden", "error")
        elif len(nueva) < 10:
            flash("La contrasena nueva debe tener al menos 10 caracteres", "error")
        elif nueva == actual:
            flash("La contrasena nueva debe ser distinta de la actual", "error")
        else:
            repositorio.cambiar_clave(usuario["id"], nueva)
            repositorio.registrar_auditoria(usuario["usuario"], "cambio_clave",
                                            usuario["usuario"], "", auth.ip_peticion())
            current_app.config["clave_provisional"] = None
            flash("Contrasena cambiada", "ok")
            return redirect(url_for("web.panel"))

    return render_template("cambiar_clave.html", titulo_pagina="Cambiar contrasena",
                           obligatorio=bool(fila["cambio_obligatorio"]))


# ------------------------------------------------------------------- panel --
@web.route("/")
@auth.requiere("ver")
def panel():
    hoy = date.today()
    ajustes = repositorio.ajustes()
    avisos = []
    if not anthropic_cliente.hay_clave():
        avisos.append("No hay clave de API de Anthropic: las publicaciones se guardan sin analisis.")
    if not correo.smtp_configurado():
        avisos.append("No hay servidor SMTP configurado: no se puede enviar el correo diario.")
    if not repositorio.destinatarios(solo_activos=True):
        avisos.append("No hay destinatarios activos.")
    if "onedrive" in str(config.DATOS).lower():
        avisos.append(f"Esta copia guarda sus datos dentro de OneDrive ({config.DATOS}). "
                      f"La sincronizacion puede corromper la base de datos y sube las claves "
                      f"cifradas a la nube. Usa la version instalada en C:\\MOVA\\Boletines "
                      f"Oficiales y no abras el .exe desde la carpeta de ejecutables.")

    if request.args.get("aviso") == "sin_permiso":
        flash("Tu rol no tiene permiso para esa pantalla", "error")

    return render_template(
        "panel.html", titulo_pagina="Panel",
        kpis=repositorio.kpis(hoy.strftime("%Y-%m-%d")),
        fecha_larga=correo.fecha_larga(hoy),
        boletines=repositorio.boletines(),
        ajustes=ajustes,
        proxima=_proxima_ejecucion(),
        proximas=_proximas(),
        cambio=_cambio(),
        tope_mensual=float(repositorio.ajuste("tope_mensual_usd", "30") or 0),
        destinatarios=len(repositorio.destinatarios(solo_activos=True)),
        recientes=repositorio.publicaciones({}, limite=25),
        avisos_configuracion=avisos,
    )


# ------------------------------------------------------------- ejecuciones --
@web.route("/ejecuciones")
@auth.requiere("ver")
def ejecuciones():
    return render_template(
        "ejecuciones.html", titulo_pagina="Ejecuciones",
        ejecuciones=repositorio.ejecuciones(),
        hoy=date.today().strftime("%Y-%m-%d"),
        detalle=None, logs=[])


@web.route("/ejecuciones/<int:ejecucion_id>")
@auth.requiere("ver")
def ejecucion(ejecucion_id: int):
    detalle = repositorio.ejecucion(ejecucion_id)
    if detalle is None:
        flash("Esa ejecucion no existe", "error")
        return redirect(url_for("web.ejecuciones"))
    return render_template(
        "ejecuciones.html", titulo_pagina=f"Ejecucion {ejecucion_id}",
        ejecuciones=repositorio.ejecuciones(),
        hoy=date.today().strftime("%Y-%m-%d"),
        detalle=detalle, logs=repositorio.logs_scraping(ejecucion_id))


@web.route("/ejecuciones/lanzar", methods=["POST"])
@auth.requiere("ejecutar")
def lanzar():
    texto_fecha = request.form.get("fecha") or ""
    try:
        objetivo = datetime.strptime(texto_fecha, "%Y-%m-%d").date() if texto_fecha else date.today()
    except ValueError:
        flash("La fecha indicada no es valida", "error")
        return redirect(url_for("web.ejecuciones"))

    usuario = auth.usuario_actual()
    tipo = "tarde" if request.form.get("tipo") == "tarde" else "manual"
    aceptada, mensaje = orquestador.lanzar(
        objetivo, tipo, usuario["usuario"],
        enviar_correo=request.form.get("enviar", "1") == "1")
    flash(mensaje, "ok" if aceptada else "error")
    return redirect(url_for("web.ejecuciones"))


@web.route("/ejecuciones/cancelar", methods=["POST"])
@auth.requiere("ejecutar")
def cancelar():
    if not orquestador.hay_ejecucion():
        flash("No hay ninguna ejecucion en curso", "error")
    else:
        orquestador.cancelar()
        flash("Cancelacion solicitada", "warn")
    return redirect(url_for("web.ejecuciones"))


@web.route("/ejecuciones/resumen-semanal", methods=["POST"])
@auth.requiere("ejecutar")
def resumen_semanal():
    usuario = auth.usuario_actual()
    enviar = request.form.get("enviar", "1") == "1"
    exito, detalle = orquestador.enviar_resumen_semanal(usuario=usuario["usuario"], enviar=enviar)
    flash(f"Resumen semanal: {detalle}", "ok" if exito else "error")
    return redirect(url_for("web.ejecuciones"))


# -------------------------------------------------------------------- coste --
@web.route("/coste")
@auth.requiere("ver")
def coste():
    queda, gasto_mes, tope = anthropic_cliente.presupuesto()
    return render_template(
        "coste.html", titulo_pagina="Coste",
        gasto_mes=gasto_mes,
        gasto_hoy=repositorio.gasto_dia_usd(),
        tope=tope,
        queda=queda,
        porcentaje=min(100, int(100 * gasto_mes / tope)) if tope > 0 else 0,
        cambio=_cambio(),
        por_modelo=repositorio.consumo_por_modelo(),
        por_dia=repositorio.consumo_por_dia(30),
        por_mes=repositorio.consumo_por_mes(12),
        ejecuciones=repositorio.ejecuciones_con_coste(30),
        precios=anthropic_cliente.PRECIOS_USD_POR_MILLON,
        modelo_extraccion=repositorio.ajuste("modelo_extraccion", "claude-sonnet-5"),
        modelo_relevancia=repositorio.ajuste("modelo_relevancia", "claude-haiku-4-5-20251001"),
        esfuerzo=repositorio.ajuste("esfuerzo_modelo", "low"),
        puede_administrar=auth.tiene_permiso("administrar"))


@web.route("/api/progreso")
@auth.requiere("ver")
def api_progreso():
    return orquestador.progreso.instantanea()


# ----------------------------------------------------------- publicaciones --
@web.route("/publicaciones")
@auth.requiere("ver")
def publicaciones():
    filtros = {
        "codigo_boletin": request.args.get("boletin", "").strip().upper() or None,
        "relevancia": request.args.get("relevancia", "").strip() or None,
        "fecha": request.args.get("fecha", "").strip() or None,
        "texto": request.args.get("texto", "").strip() or None,
    }
    limpios = {clave: valor for clave, valor in filtros.items() if valor}
    filas = repositorio.publicaciones(limpios, limite=400)
    return render_template(
        "publicaciones.html", titulo_pagina="Publicaciones",
        publicaciones=filas,
        documentos=repositorio.documentos_de([fila["id"] for fila in filas]),
        boletines=repositorio.boletines(),
        filtros=filtros,
        puede_editar=auth.tiene_permiso("editar"),
        puede_descartar=auth.tiene_permiso("descartar"))


# ------------------------------------------ resumen corto, ampliado, infografia --
def _pagina_estado(fila, tipo: str, estado: str, mensaje: str = "", codigo: int = 200):
    return render_template(
        "documento_estado.html", titulo_pagina=documentos.TIPOS[tipo][0],
        rotulo=documentos.TIPOS[tipo][0], publicacion=fila, estado=estado, mensaje=mensaje,
        refrescar=(estado == "generando"),
        puede_generar=auth.tiene_permiso("ejecutar"),
        url_reintentar=url_for("web.documento", publicacion_id=fila["id"], tipo=tipo,
                               reintentar=1)), codigo


@web.route("/publicaciones/<int:publicacion_id>/documento/<tipo>")
@auth.requiere("ver")
def documento(publicacion_id: int, tipo: str):
    """Muestra el documento; si aun no existe, lo genera (una vez para los tres)."""
    if tipo not in documentos.TIPOS:
        return redirect(url_for("web.publicaciones"))
    fila = repositorio.publicacion(publicacion_id)
    if fila is None:
        flash("Esa publicacion no existe", "error")
        return redirect(url_for("web.publicaciones"))

    doc = repositorio.documento(publicacion_id)
    if doc is not None and doc["estado"] == "listo" and not request.args.get("reintentar"):
        datos = json.loads(doc["datos_json"] or "{}")
        barra = {
            "volver": url_for("web.publicaciones"),
            "url_tipo": {t: url_for("web.documento", publicacion_id=publicacion_id, tipo=t)
                         for t in documentos.TIPOS},
            "descargar": url_for("web.descargar_documento", publicacion_id=publicacion_id,
                                 tipo=tipo),
            "regenerar": (url_for("web.regenerar_documento", publicacion_id=publicacion_id)
                          if auth.tiene_permiso("ejecutar") else ""),
            "nota": f"{doc['paginas']} pag. analizadas con {doc['modelo']}",
        }
        return documentos.renderizar(tipo, datos, dict(fila), barra)

    if documentos.generando(publicacion_id):
        return _pagina_estado(fila, tipo, "generando")

    if doc is not None and doc["estado"] == "error" and not request.args.get("reintentar"):
        return _pagina_estado(fila, tipo, "error", doc["error"])

    if not auth.tiene_permiso("ejecutar"):
        return _pagina_estado(fila, tipo, "sin_permiso", codigo=403)

    usuario = auth.usuario_actual()
    aceptada, mensaje = documentos.lanzar(publicacion_id, usuario["usuario"])
    if not aceptada:
        return _pagina_estado(fila, tipo, "error", mensaje)
    return _pagina_estado(fila, tipo, "generando")


def _respuesta_descarga(tipo: str, doc, fila) -> Response:
    contenido, mime, nombre = documentos.descarga(
        tipo, json.loads(doc["datos_json"] or "{}"), dict(fila))
    return Response(contenido, mimetype=mime,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@web.route("/publicaciones/<int:publicacion_id>/documento/<tipo>/descargar")
@auth.requiere("ver")
def descargar_documento(publicacion_id: int, tipo: str):
    fila = repositorio.publicacion(publicacion_id)
    doc = repositorio.documento(publicacion_id)
    if tipo not in documentos.TIPOS or fila is None or doc is None or doc["estado"] != "listo":
        flash("El documento todavia no esta generado", "error")
        return redirect(url_for("web.publicaciones"))
    return _respuesta_descarga(tipo, doc, fila)


@web.route("/publicaciones/<int:publicacion_id>/documento/regenerar", methods=["POST"])
@auth.requiere("ejecutar")
def regenerar_documento(publicacion_id: int):
    usuario = auth.usuario_actual()
    aceptada, mensaje = documentos.lanzar(publicacion_id, usuario["usuario"])
    flash(mensaje, "ok" if aceptada else "error")
    return redirect(url_for("web.documento", publicacion_id=publicacion_id, tipo="corto"))


# --------------------- botones del correo: acceso con clave, sin iniciar sesion --
# Quien recibe el correo puede generar y ver los tres documentos de ESA
# publicacion. La clave no da acceso a nada mas de la herramienta, no permite
# regenerar (la IA se paga una vez por publicacion) y caduca a los 90 dias.
INTENTOS_MAX_DOCUMENTO = 200  # por IP y ventana: la pagina de espera se refresca sola


def _publicacion_por_clave(token: str, tipo: str):
    """Devuelve (fila, None) si la clave vale, o (None, respuesta de error)."""
    ip = auth.ip_peticion()
    repositorio.registrar_intento_ip(ip, "documento")
    if repositorio.intentos_recientes(ip, VENTANA_INTENTOS, "documento") > INTENTOS_MAX_DOCUMENTO:
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
    repositorio.usar_token_documento(token, ip)
    return fila, None


@web.route("/d/<token>/<tipo>")
def documento_por_clave(token: str, tipo: str):
    fila, error = _publicacion_por_clave(token, tipo)
    if error:
        return error

    doc = repositorio.documento(fila["id"])
    if doc is not None and doc["estado"] == "listo":
        barra = {
            "volver": "",
            "url_tipo": {t: url_for("web.documento_por_clave", token=token, tipo=t)
                         for t in documentos.TIPOS},
            "descargar": url_for("web.descargar_por_clave", token=token, tipo=tipo),
            "regenerar": "",
            "nota": f"{doc['paginas']} pag. analizadas",
        }
        return documentos.renderizar(tipo, json.loads(doc["datos_json"] or "{}"), dict(fila), barra)

    def estado(nombre: str, mensaje: str = ""):
        return render_template(
            "documento_estado.html", titulo_pagina=documentos.TIPOS[tipo][0],
            rotulo=documentos.TIPOS[tipo][0], publicacion=fila, estado=nombre, mensaje=mensaje,
            refrescar=(nombre == "generando"), puede_generar=True,
            url_reintentar=url_for("web.documento_por_clave", token=token, tipo=tipo,
                                   reintentar=1))

    if documentos.generando(fila["id"]):
        return estado("generando")
    if doc is not None and doc["estado"] == "error" and not request.args.get("reintentar"):
        return estado("error", doc["error"])

    aceptada, mensaje = documentos.lanzar(fila["id"], f"correo ({auth.ip_peticion()})")
    return estado("generando") if aceptada else estado("error", mensaje)


@web.route("/d/<token>/<tipo>/descargar")
def descargar_por_clave(token: str, tipo: str):
    fila, error = _publicacion_por_clave(token, tipo)
    if error:
        return error
    doc = repositorio.documento(fila["id"])
    if doc is None or doc["estado"] != "listo":
        return redirect(url_for("web.documento_por_clave", token=token, tipo=tipo))
    return _respuesta_descarga(tipo, doc, fila)


@web.route("/publicaciones/<int:publicacion_id>/descartar")
@auth.requiere("descartar")
def descartar_manual(publicacion_id: int):
    usuario = auth.usuario_actual()
    if repositorio.descartar(publicacion_id, "interfaz", usuario=usuario["usuario"],
                             ip=auth.ip_peticion()):
        repositorio.registrar_auditoria(usuario["usuario"], "descarte_manual",
                                        str(publicacion_id), "", auth.ip_peticion())
        flash("Publicacion descartada", "ok")
    else:
        flash("No se encontro la publicacion", "error")
    return redirect(request.referrer or url_for("web.publicaciones"))


@web.route("/publicaciones/reenviar", methods=["POST"])
@auth.requiere("editar")
def reenviar():
    ids = [int(valor) for valor in request.form.getlist("ids") if valor.isdigit()]
    if not ids:
        flash("No has seleccionado ninguna publicacion", "error")
        return redirect(url_for("web.publicaciones"))
    usuario = auth.usuario_actual()
    exito, detalle = orquestador.reenviar(ids, usuario["usuario"])
    flash(detalle, "ok" if exito else "error")
    return redirect(url_for("web.publicaciones"))


# ---------------------------------------------------------------- descartes --
@web.route("/descartes")
@auth.requiere("ver")
def descartes():
    return render_template("descartes.html", titulo_pagina="Descartes",
                           descartes=repositorio.descartes(),
                           puede_descartar=auth.tiene_permiso("descartar"))


@web.route("/descartes/<int:descarte_id>/recuperar")
@auth.requiere("descartar")
def recuperar_descarte(descarte_id: int):
    usuario = auth.usuario_actual()
    if repositorio.recuperar_descarte(descarte_id):
        repositorio.registrar_auditoria(usuario["usuario"], "recuperar_descarte",
                                        str(descarte_id), "", auth.ip_peticion())
        flash("Publicacion recuperada", "ok")
    else:
        flash("No se encontro ese descarte", "error")
    return redirect(url_for("web.descartes"))


# -------------------------------- ruta publica de descarte (unica sin sesion) --
@web.route("/descartar/<token>")
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


# ---------------------------------------------------------------- boletines --
@web.route("/boletines")
@auth.requiere("ver")
def boletines():
    return render_template("boletines.html", titulo_pagina="Boletines",
                           boletines=repositorio.boletines(),
                           fichas={ficha["codigo"]: ficha for ficha in fichas()},
                           puede_editar=auth.tiene_permiso("editar"))


@web.route("/boletines/<codigo>/cambiar")
@auth.requiere("editar")
def cambiar_boletin(codigo: str):
    ficha = repositorio.boletin(codigo.upper())
    if ficha is None:
        flash("Ese boletin no existe", "error")
    else:
        repositorio.activar_boletin(ficha["codigo"], not ficha["activo"])
        usuario = auth.usuario_actual()
        repositorio.registrar_auditoria(usuario["usuario"], "cambiar_boletin", ficha["codigo"],
                                        f"activo={not ficha['activo']}", auth.ip_peticion())
        flash(f"Boletin {ficha['codigo']} actualizado", "ok")
    return redirect(url_for("web.boletines"))


# ----------------------------------------------------------- palabras clave --
@web.route("/palabras-clave", methods=["GET", "POST"])
@auth.requiere("ver")
def palabras():
    if request.method == "POST":
        if not auth.tiene_permiso("editar"):
            flash("Tu rol no puede editar las palabras clave", "error")
            return redirect(url_for("web.palabras"))
        termino = (request.form.get("termino") or "").strip()
        if not termino:
            flash("Escribe un termino", "error")
        else:
            refuerzo = request.form.get("tipo") == "refuerzo"
            repositorio.anadir_palabra(termino, refuerzo)
            usuario = auth.usuario_actual()
            repositorio.registrar_auditoria(usuario["usuario"], "anadir_palabra", termino,
                                            f"refuerzo={refuerzo}", auth.ip_peticion())
            flash(f"Termino '{termino}' anadido", "ok")
        return redirect(url_for("web.palabras"))

    return render_template("palabras_clave.html", titulo_pagina="Palabras clave",
                           palabras=repositorio.palabras_clave(solo_activas=False),
                           puede_editar=auth.tiene_permiso("editar"))


@web.route("/palabras-clave/<int:palabra_id>/cambiar")
@auth.requiere("editar")
def cambiar_palabra(palabra_id: int):
    actuales = {fila["id"]: fila for fila in repositorio.palabras_clave(solo_activas=False)}
    fila = actuales.get(palabra_id)
    if fila is None:
        flash("Ese termino no existe", "error")
    else:
        repositorio.activar_palabra(palabra_id, not fila["activa"])
        flash("Termino actualizado", "ok")
    return redirect(url_for("web.palabras"))


@web.route("/palabras-clave/<int:palabra_id>/borrar")
@auth.requiere("editar")
def borrar_palabra(palabra_id: int):
    repositorio.borrar_palabra(palabra_id)
    usuario = auth.usuario_actual()
    repositorio.registrar_auditoria(usuario["usuario"], "borrar_palabra", str(palabra_id), "",
                                    auth.ip_peticion())
    flash("Termino borrado", "ok")
    return redirect(url_for("web.palabras"))


# ------------------------------------------------------------ destinatarios --
@web.route("/destinatarios", methods=["GET", "POST"])
@auth.requiere("ver")
def destinatarios():
    if request.method == "POST":
        if not auth.tiene_permiso("editar"):
            flash("Tu rol no puede editar los destinatarios", "error")
            return redirect(url_for("web.destinatarios"))
        direccion = (request.form.get("correo") or "").strip().lower()
        if "@" not in direccion or "." not in direccion.split("@")[-1]:
            flash("Esa direccion de correo no es valida", "error")
        else:
            repositorio.anadir_destinatario(direccion, (request.form.get("nombre") or "").strip())
            usuario = auth.usuario_actual()
            repositorio.registrar_auditoria(usuario["usuario"], "anadir_destinatario", direccion,
                                            "", auth.ip_peticion())
            flash("Destinatario anadido", "ok")
        return redirect(url_for("web.destinatarios"))

    return render_template("destinatarios.html", titulo_pagina="Destinatarios",
                           destinatarios=repositorio.destinatarios(solo_activos=False),
                           puede_editar=auth.tiene_permiso("editar"))


@web.route("/destinatarios/<int:destinatario_id>/cambiar")
@auth.requiere("editar")
def cambiar_destinatario(destinatario_id: int):
    actuales = {fila["id"]: fila for fila in repositorio.destinatarios(solo_activos=False)}
    fila = actuales.get(destinatario_id)
    if fila is None:
        flash("Ese destinatario no existe", "error")
    else:
        repositorio.activar_destinatario(destinatario_id, not fila["activo"])
        flash("Destinatario actualizado", "ok")
    return redirect(url_for("web.destinatarios"))


@web.route("/destinatarios/<int:destinatario_id>/borrar")
@auth.requiere("editar")
def borrar_destinatario(destinatario_id: int):
    repositorio.borrar_destinatario(destinatario_id)
    usuario = auth.usuario_actual()
    repositorio.registrar_auditoria(usuario["usuario"], "borrar_destinatario",
                                    str(destinatario_id), "", auth.ip_peticion())
    flash("Destinatario borrado", "ok")
    return redirect(url_for("web.destinatarios"))


# ----------------------------------------------------------------- usuarios --
@web.route("/usuarios", methods=["GET", "POST"])
@auth.requiere("administrar")
def usuarios():
    if request.method == "POST":
        nombre_usuario = (request.form.get("usuario") or "").strip().lower()
        clave = request.form.get("clave") or ""
        rol = request.form.get("rol") or "consulta"
        if not nombre_usuario or len(clave) < 10:
            flash("Hace falta usuario y una contrasena de al menos 10 caracteres", "error")
        elif rol not in config.ROLES:
            flash("Rol no valido", "error")
        elif repositorio.usuario_por_nombre(nombre_usuario):
            flash("Ya existe un usuario con ese nombre", "error")
        else:
            repositorio.crear_usuario(nombre_usuario, clave, rol,
                                      (request.form.get("nombre") or "").strip(),
                                      (request.form.get("correo") or "").strip(),
                                      cambio_obligatorio=True)
            actual = auth.usuario_actual()
            repositorio.registrar_auditoria(actual["usuario"], "crear_usuario", nombre_usuario,
                                            f"rol={rol}", auth.ip_peticion())
            flash(f"Usuario {nombre_usuario} creado; debera cambiar la contrasena al entrar", "ok")
        return redirect(url_for("web.usuarios"))

    return render_template("usuarios.html", titulo_pagina="Usuarios",
                           usuarios=repositorio.usuarios(),
                           roles=config.ROLES,
                           descripcion_roles=auth.DESCRIPCION_ROLES,
                           auditoria=repositorio.auditoria(150))


@web.route("/usuarios/<int:usuario_id>/cambiar", methods=["POST"])
@auth.requiere("administrar")
def cambiar_usuario(usuario_id: int):
    fila = repositorio.usuario_por_id(usuario_id)
    if fila is None:
        flash("Ese usuario no existe", "error")
        return redirect(url_for("web.usuarios"))

    rol = request.form.get("rol") or fila["rol"]
    activo = request.form.get("activo") == "1"
    if rol not in config.ROLES:
        flash("Rol no valido", "error")
        return redirect(url_for("web.usuarios"))

    quedaria_sin_admin = (fila["rol"] == "administrador" and fila["activo"]
                          and (rol != "administrador" or not activo)
                          and repositorio.administradores_activos(excluyendo=usuario_id) == 0)
    if quedaria_sin_admin:
        flash("No se puede dejar el sistema sin el ultimo administrador activo", "error")
        return redirect(url_for("web.usuarios"))

    repositorio.actualizar_usuario(usuario_id, fila["nombre"], fila["correo"], rol, activo)
    actual = auth.usuario_actual()
    repositorio.registrar_auditoria(actual["usuario"], "cambiar_usuario", fila["usuario"],
                                    f"rol={rol}; activo={activo}", auth.ip_peticion())
    flash("Usuario actualizado", "ok")
    return redirect(url_for("web.usuarios"))


@web.route("/usuarios/<int:usuario_id>/reiniciar-clave", methods=["POST"])
@auth.requiere("administrar")
def reiniciar_clave(usuario_id: int):
    fila = repositorio.usuario_por_id(usuario_id)
    if fila is None:
        flash("Ese usuario no existe", "error")
        return redirect(url_for("web.usuarios"))
    provisional = secrets.token_urlsafe(9)
    repositorio.cambiar_clave(usuario_id, provisional)
    repositorio.actualizar_usuario(usuario_id, fila["nombre"], fila["correo"], fila["rol"],
                                   bool(fila["activo"]))
    repositorio.forzar_cambio_clave(usuario_id)
    actual = auth.usuario_actual()
    repositorio.registrar_auditoria(actual["usuario"], "reiniciar_clave", fila["usuario"], "",
                                    auth.ip_peticion())
    flash(f"Contrasena provisional de {fila['usuario']}: {provisional}", "warn")
    return redirect(url_for("web.usuarios"))


# ------------------------------------------------------------------ ajustes --
_AJUSTES_TEXTO = ("modelo_extraccion", "modelo_relevancia", "max_tokens_extraccion",
                  "max_tokens_relevancia", "hilos_modelo", "smtp_servidor", "smtp_puerto",
                  "smtp_seguridad", "smtp_usuario", "smtp_remitente", "smtp_nombre_remitente",
                  "url_publica", "hora_ejecucion", "dias_ejecucion", "planificador_activo",
                  "recuperacion_activa", "dias_recuperacion",
                  "umbral_difuso", "dias_dedup", "dias_token_descarte", "reintentos_boletin",
                  "copias_max", "max_candidatas_ejecucion", "terminos_refuerzo",
                  "tarde_activa", "hora_tarde", "alerta_activa", "dias_alerta",
                  "semanal_activo", "dia_semanal", "hora_semanal", "dias_vencimiento_semanal",
                  "esfuerzo_modelo", "tope_mensual_usd", "cambio_usd_eur",
                  "modelo_documentos", "max_tokens_documentos")


@web.route("/ajustes", methods=["GET", "POST"])
@auth.requiere("administrar")
def ajustes():
    if request.method == "POST":
        for clave in _AJUSTES_TEXTO:
            if clave in request.form:
                repositorio.guardar_ajuste(clave, (request.form.get(clave) or "").strip())

        clave_api_nueva = (request.form.get("anthropic_api_key") or "").strip()
        if clave_api_nueva:  # vacio = no tocar lo ya guardado
            try:
                clave_api_nueva, aviso_clave = anthropic_cliente.normalizar_clave(clave_api_nueva)
                repositorio.guardar_ajuste("anthropic_api_key", clave_api_nueva)
                if aviso_clave:
                    flash(aviso_clave, "warn")
                correcta, mensaje_clave = anthropic_cliente.probar_clave()
                flash(mensaje_clave, "ok" if correcta else "error")
            except anthropic_cliente.ErrorModelo as error:
                flash(str(error), "error")
        clave_smtp_nueva = (request.form.get("smtp_clave") or "").strip()
        if clave_smtp_nueva:
            repositorio.guardar_ajuste("smtp_clave", clave_smtp_nueva)

        if (request.form.get("modelo_extraccion") not in config.MODELOS_DISPONIBLES
                or request.form.get("modelo_relevancia") not in config.MODELOS_DISPONIBLES):
            flash("El modelo elegido no esta en la lista admitida", "warn")

        usuario = auth.usuario_actual()
        repositorio.registrar_auditoria(usuario["usuario"], "guardar_ajustes", "",
                                        "Ajustes actualizados", auth.ip_peticion())
        reprogramar = current_app.config.get("reprogramar")
        if reprogramar:
            reprogramar()
        flash("Ajustes guardados", "ok")
        return redirect(url_for("web.ajustes"))

    guardados = repositorio.ajustes()
    clave = anthropic_cliente.clave_api()
    return render_template(
        "ajustes.html", titulo_pagina="Ajustes", ajustes=guardados,
        modelos=config.MODELOS_DISPONIBLES,
        pista_api=(clave[:7] + "..." + clave[-4:]) if clave else "",
        smtp_clave_guardada=repositorio.ajuste_esta_definido("smtp_clave"),
        hay_api=anthropic_cliente.hay_clave(),
        smtp_ok=correo.smtp_configurado(),
        hay_ocr=tesseract_disponible(),
        url_publica_efectiva=correo.url_publica(),
        ruta_clave=str(config.RUTA_CLAVE),
        proxima=_proxima_ejecucion(),
        proxima_tarde=_proxima_ejecucion("vigilancia_tarde"),
        proxima_semanal=_proxima_ejecucion("resumen_semanal"),
        gasto_mes=repositorio.gasto_mes_usd())


@web.route("/ajustes/probar-api", methods=["POST"])
@auth.requiere("administrar")
def probar_api():
    modelo = repositorio.ajuste("modelo_relevancia", "claude-haiku-4-5-20251001")
    correcto, mensaje = anthropic_cliente.probar_clave(modelo)
    flash(mensaje, "ok" if correcto else "error")
    return redirect(url_for("web.ajustes"))


@web.route("/ajustes/probar-correo", methods=["POST"])
@auth.requiere("administrar")
def probar_correo():
    direcciones = [fila["correo"] for fila in repositorio.destinatarios(solo_activos=True)]
    html = correo.componer([], date.today(), {"consultados": [], "fallidos": []})
    exito, detalle, intentos = correo.enviar(direcciones, "[MOVA Boletines] Correo de prueba", html)
    repositorio.registrar_envio(None, ", ".join(direcciones), "Correo de prueba",
                                "enviado" if exito else "error", intentos, detalle, 0, "")
    flash(detalle, "ok" if exito else "error")
    return redirect(url_for("web.ajustes"))


# ------------------------------------------------------------------- copias --
@web.route("/copias", methods=["GET", "POST"])
@auth.requiere("administrar")
def copias():
    if request.method == "POST":
        usuario = auth.usuario_actual()
        try:
            destino = copias_datos.crear_copia("manual", usuario["usuario"])
            flash(f"Copia creada: {destino.name}", "ok")
        except Exception as error:  # noqa: BLE001
            flash(f"No se pudo crear la copia: {error}", "error")
        return redirect(url_for("web.copias"))

    return render_template("copias.html", titulo_pagina="Copias de seguridad",
                           copias=copias_datos.listar(),
                           maximo=repositorio.ajuste_int("copias_max", 10))


@web.route("/copias/restaurar", methods=["POST"])
@auth.requiere("administrar")
def restaurar():
    nombre = (request.form.get("nombre") or "").strip()
    usuario = auth.usuario_actual()
    correcto, mensaje = copias_datos.restaurar(nombre, usuario["usuario"])
    flash(mensaje, "ok" if correcto else "error")
    return redirect(url_for("web.copias"))


@web.route("/exportar/<formato>")
@auth.requiere("ver")
def exportar(formato: str):
    usuario = auth.usuario_actual()
    try:
        if formato == "xlsx":
            destino = copias_datos.exportar_excel()
        elif formato == "json":
            destino = copias_datos.exportar_json()
        else:
            flash("Formato no admitido", "error")
            return redirect(url_for("web.publicaciones"))
    except Exception as error:  # noqa: BLE001
        flash(f"No se pudo exportar: {error}", "error")
        return redirect(url_for("web.publicaciones"))

    repositorio.registrar_auditoria(usuario["usuario"], "exportar", formato, destino.name,
                                    auth.ip_peticion())
    return send_file(destino, as_attachment=True, download_name=destino.name)


@web.route("/salud")
def salud():
    """Comprobacion para el servidor o el balanceador; no expone datos."""
    return Response("ok", mimetype="text/plain")
