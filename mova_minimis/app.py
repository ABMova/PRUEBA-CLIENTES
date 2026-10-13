"""MOVA Minimis · punto de entrada.

python app.py  ->  aplica el esquema, hace copia de seguridad, levanta waitress
en 127.0.0.1:5000 y abre el navegador.
"""
import os
import logging
import secrets
import socket
import sys
import threading
import webbrowser
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, abort, g, jsonify, render_template, request, session

import config
from auth import permissions, user
from models import db

log = logging.getLogger("mova_minimis")


def _configurar_registro() -> None:
    config.preparar_carpetas()
    manejador = RotatingFileHandler(config.DIR_LOGS / "app.log", maxBytes=2_000_000, backupCount=5,
                                    encoding="utf-8")
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(manejador)
    if not config.CONGELADO:
        raiz.addHandler(logging.StreamHandler(sys.stdout))


def _asegurar_admin() -> None:
    if config.ESCRITORIO:
        return  # en escritorio no hay inicio de sesión: el usuario es la cuenta de Windows
    # El usuario del equipo (versión de escritorio) no cuenta: con la misma base en modo servidor
    # hace falta igualmente alguien que pueda entrar por /login
    if not any(u["email"] != config.EMAIL_ESCRITORIO for u in db.listar_usuarios()):
        db.crear_usuario(config.ADMIN_INICIAL_EMAIL, "Administrador", user.hash_clave(config.ADMIN_INICIAL_CLAVE),
                         "admin", cambiar_clave=1)
        log.info("Creado el usuario inicial %s (cambio de contraseña obligatorio)", config.ADMIN_INICIAL_EMAIL)


def _secreto_sesion() -> str:
    s = db.leer_ajuste("secreto_sesion")
    if not s:
        s = secrets.token_hex(32)
        db.guardar_ajuste("secreto_sesion", s)
    return s


def ip_cliente() -> str:
    if config.DETRAS_DE_PROXY:
        return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "")
    return request.remote_addr or ""


def crear_app() -> Flask:
    db.inicializar()
    _asegurar_admin()

    app = Flask(__name__, template_folder=str(config.RAIZ_CODIGO / "templates"),
                static_folder=str(config.RAIZ_CODIGO / "static"))
    app.config.update(
        SECRET_KEY=_secreto_sesion(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_NAME="mova_minimis",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=config.HORAS_SESION),
        MAX_CONTENT_LENGTH=config.MAX_SUBIDA_MB * 1024 * 1024 * 10,
    )

    from routes import admin, auth as rutas_auth, consultas, dashboard, resultados
    for bp in (rutas_auth.bp, dashboard.bp, consultas.bp, resultados.bp, admin.bp):
        app.register_blueprint(bp)

    @app.before_request
    def antes():
        if config.ESCRITORIO:
            # Solo la ventana de la aplicación: trae el token que generó al arrancar y llama a 127.0.0.1.
            # Así ni otro programa del equipo ni una web abierta en el navegador pueden usar el puerto.
            enviado = request.headers.get("X-MOVA-Token", "")
            if not config.TOKEN_ESCRITORIO or not secrets.compare_digest(enviado, config.TOKEN_ESCRITORIO):
                abort(403)
            if request.host != f"127.0.0.1:{config.PUERTO}":
                abort(403)
        permissions.cargar_usuario()
        g.ip = ip_cliente()
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        if request.method in ("POST", "PUT", "DELETE"):
            enviado = request.headers.get("X-CSRF") or request.form.get("csrf")
            if not enviado or not secrets.compare_digest(enviado, session["csrf"]):
                abort(400, "Formulario caducado: recargue la página e inténtelo de nuevo.")

    @app.after_request
    def cabeceras(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def globales():
        return {"usuario": g.get("usuario"), "puede": permissions.puede,
                "version": config.VERSION, "csrf": session.get("csrf", ""), "ROLES": permissions.ROLES,
                "ultima_consulta": session.get("ultima_consulta"), "escritorio": config.ESCRITORIO,
                "config_desbloqueada": permissions.configuracion_desbloqueada()}

    @app.template_filter("euros")
    def filtro_euros(x):
        from logic.calculador import euros
        return euros(x)

    @app.template_filter("fecha")
    def filtro_fecha(iso):
        from datetime import datetime
        if not iso:
            return ""
        try:
            if "T" in iso:
                return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
            return datetime.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return iso

    @app.route("/escritorio/cerrar")
    def cerrar_escritorio():
        """La ventana lo pide al cerrarse (protegido por el token, como todo en escritorio)."""
        if not config.ESCRITORIO:
            abort(404)
        threading.Timer(0.3, _salir).start()
        return {"ok": True}

    @app.route("/salud")
    def salud():
        """La ventana de escritorio espera a que esto responda antes de mostrar la aplicación."""
        return {"ok": True, "version": config.VERSION}

    def _error(codigo, titulo):
        def manejador(e):
            if request.path.startswith("/api/"):
                return jsonify({"error": getattr(e, "description", titulo)}), codigo
            return render_template("error.html", codigo=codigo, titulo=titulo,
                                   detalle=getattr(e, "description", "")), codigo
        return manejador

    app.register_error_handler(400, _error(400, "Petición no válida"))
    app.register_error_handler(403, _error(403, "Sin permiso para esta acción"))
    app.register_error_handler(404, _error(404, "Página no encontrada"))
    app.register_error_handler(413, _error(413, "Fichero demasiado grande"))

    @app.errorhandler(500)
    def error_500(e):
        log.exception("Error interno en %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Error interno. Consulte data/logs/app.log."}), 500
        return render_template("error.html", codigo=500, titulo="Error interno",
                               detalle="Se ha registrado en el fichero de registro."), 500

    return app


def _vaciar_temporal() -> None:
    """Restos de subidas o descargas cortadas por un cierre a destiempo."""
    import shutil
    for p in config.DIR_TEMPORAL.iterdir():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)


def _puerto_ocupado(host, puerto) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, puerto)) == 0


def _vigilar_padre(pid: int) -> None:
    """En escritorio: si la ventana Electron muere sin cerrar el servidor, el servidor se cierra solo."""
    import ctypes
    SYNCHRONIZE = 0x00100000
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        log.warning("No se encuentra el proceso de la ventana (%s): el servidor se cierra.", pid)
        os._exit(0)
    k32.WaitForSingleObject(h, 0xFFFFFFFF)  # espera a que termine, sin consumir nada
    log.info("La ventana se cerró: el servidor se cierra.")
    _salir()


def _salir() -> None:
    """Cierre del motor de escritorio: primero el Word invisible, que si no quedaría vivo."""
    from integrations import word_pdf
    word_pdf.cerrar_word()
    os._exit(0)


def main() -> None:
    _configurar_registro()
    url = f"http://{config.HOST}:{config.PUERTO}"
    if config.ESCRITORIO:
        if not config.TOKEN_ESCRITORIO:
            log.error("Modo escritorio sin MOVA_TOKEN: no se arranca.")
            sys.exit(2)
        if config.PID_PADRE and os.name == "nt":
            threading.Thread(target=_vigilar_padre, args=(config.PID_PADRE,), daemon=True).start()
    elif _puerto_ocupado(config.HOST, config.PUERTO):
        log.info("Ya hay una instancia en %s; se abre el navegador y se sale.", url)
        if config.ABRIR_NAVEGADOR:
            webbrowser.open(url)
        return
    app = crear_app()
    _vaciar_temporal()
    n = db.marcar_interrumpidas()
    if n:
        log.warning("%d consulta(s) en curso marcadas como interrumpidas", n)
    try:
        copia = db.copia_automatica()
        log.info("Copia de seguridad al arrancar: %s", copia.name)
    except Exception:
        log.exception("No se pudo hacer la copia de seguridad al arrancar")
    log.info("MOVA Minimis %s en %s · datos en %s", config.VERSION, url, config.DATOS)
    if config.ABRIR_NAVEGADOR and not config.ESCRITORIO:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    from waitress import serve
    kwargs = {"trusted_proxy": "127.0.0.1", "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"}} \
        if config.DETRAS_DE_PROXY else {}
    serve(app, host=config.HOST, port=config.PUERTO, threads=8, **kwargs)


if __name__ == "__main__":
    main()
