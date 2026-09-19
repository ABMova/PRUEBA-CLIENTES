"""Arranque de MOVA Boletines Oficiales.

IMPORTANTE: un solo proceso con varios hilos. El progreso de la ejecucion vive
en memoria, asi que con varios workers la interfaz veria estados distintos.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import logging.handlers
import os
import secrets
import socket
import sys
import threading
import webbrowser
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask, render_template, request
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from datos import copias, repositorio
from negocio import orquestador, recuperacion
from web.rutas import web as plano_web

registro = logging.getLogger("mova")


# ------------------------------------------------------------------ registro --
def preparar_registro() -> None:
    config.preparar_carpetas()
    # El .exe no tiene ventana: sin esto, cualquier escritura en consola fallaria.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    fichero = logging.handlers.RotatingFileHandler(
        config.RUTA_REGISTROS / "mova.log", maxBytes=2_000_000, backupCount=10,
        encoding="utf-8")
    fichero.setFormatter(formato)

    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.handlers.clear()
    raiz.setLevel(getattr(logging, config.LOG_NIVEL, logging.INFO))
    raiz.addHandler(fichero)
    raiz.addHandler(consola)

    # Las librerias de red son muy habladoras; no aportan nada al registro.
    for ruidosa in ("urllib3", "apscheduler.executors.default", "httpx", "pdfminer"):
        logging.getLogger(ruidosa).setLevel(logging.WARNING)


# --------------------------------------------------------------- secreto web --
def secreto_persistente() -> bytes:
    """Secreto de sesion estable entre reinicios (si cambiara, todos fuera)."""
    ruta = config.DATOS / "sesion.key"
    if not ruta.exists():
        ruta.write_bytes(secrets.token_bytes(32))
    return ruta.read_bytes()


# ------------------------------------------------------------- planificador --
def _tarea_programada() -> None:
    """Dispara el pipeline a la hora fijada, para el dia en curso."""
    if repositorio.ajuste("planificador_activo", "1") != "1":
        registro.info("Disparo automatico desactivado en Ajustes; no se ejecuta")
        return
    aceptada, mensaje = orquestador.lanzar(date.today(), "programada", "planificador")
    registro.info("Disparo programado: %s", mensaje)


def _tarea_tarde() -> None:
    """Segunda pasada del dia: boletines extraordinarios o publicados tarde.

    Revisa los mismos boletines del dia en curso. La deduplicacion deja fuera
    todo lo que ya salio por la manana, asi que solo llega lo nuevo, y si no hay
    nada no se envia correo.
    """
    if repositorio.ajuste("planificador_activo", "1") != "1":
        return
    if repositorio.ajuste("tarde_activa", "1") != "1":
        return
    aceptada, mensaje = orquestador.lanzar(date.today(), "tarde", "planificador")
    registro.info("Comprobacion de la tarde: %s", mensaje)


def _tarea_semanal() -> None:
    if repositorio.ajuste("semanal_activo", "1") != "1":
        return
    exito, detalle = orquestador.enviar_resumen_semanal()
    registro.info("Resumen semanal: %s", detalle)
    repositorio.cerrar_conexion()


def _tarea_recuperacion() -> None:
    """Lo que no se hizo porque el equipo estaba apagado o dormido a su hora."""
    try:
        hecho = recuperacion.recuperar()
        if hecho:
            registro.info("Recuperado: %s", ", ".join(hecho))
    except Exception:  # noqa: BLE001 - un fallo aqui no debe parar el planificador
        registro.exception("Fallo al recuperar lo pendiente")


def _disparo(hora: str, dias: str, zona: str, por_defecto: tuple[int, int]) -> CronTrigger:
    try:
        horas, minutos = hora.split(":")
        return CronTrigger(day_of_week=dias, hour=int(horas), minute=int(minutos), timezone=zona)
    except ValueError:
        registro.error("Horario no valido (%s %s); se usa %02d:%02d", hora, dias, *por_defecto)
        return CronTrigger(day_of_week=dias if dias else "mon-fri", hour=por_defecto[0],
                           minute=por_defecto[1], timezone=zona)


def configurar_planificador(aplicacion: Flask) -> BackgroundScheduler:
    planificador = BackgroundScheduler(timezone=repositorio.ajuste("zona_horaria",
                                                                   config.ZONA_HORARIA))
    planificador.start()

    def reprogramar() -> None:
        planificador.remove_all_jobs()
        zona = repositorio.ajuste("zona_horaria", config.ZONA_HORARIA)
        dias = repositorio.ajuste("dias_ejecucion", "mon-fri")
        comunes = {"replace_existing": True, "misfire_grace_time": 3600, "coalesce": True,
                   "max_instances": 1}

        planificador.add_job(
            _tarea_programada,
            _disparo(repositorio.ajuste("hora_ejecucion", "07:45"), dias, zona, (7, 45)),
            id="vigilancia_diaria", name="Vigilancia de la manana", **comunes)

        if repositorio.ajuste("tarde_activa", "1") == "1":
            planificador.add_job(
                _tarea_tarde,
                _disparo(repositorio.ajuste("hora_tarde", "20:00"), dias, zona, (20, 0)),
                id="vigilancia_tarde", name="Comprobacion de la tarde", **comunes)

        if repositorio.ajuste("semanal_activo", "1") == "1":
            planificador.add_job(
                _tarea_semanal,
                _disparo(repositorio.ajuste("hora_semanal", "08:30"),
                         repositorio.ajuste("dia_semanal", "mon"), zona, (8, 30)),
                id="resumen_semanal", name="Resumen semanal", **comunes)

        if config.RECUPERACION:
            # Al encender (con 2 minutos para que llegue la red) y cada 10 minutos,
            # lo que cubre tambien la vuelta de la suspension.
            planificador.add_job(
                _tarea_recuperacion, IntervalTrigger(minutes=10, timezone=zona),
                next_run_time=datetime.now(planificador.timezone) + timedelta(minutes=2),
                id="recuperacion", name="Recuperacion de lo pendiente",
                replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=600)

        for trabajo in planificador.get_jobs():
            if trabajo.next_run_time and trabajo.id != "recuperacion":
                registro.info("Proxima %s: %s", trabajo.name.lower(),
                              trabajo.next_run_time.strftime("%d/%m/%Y %H:%M %Z"))

    reprogramar()
    aplicacion.config["planificador"] = planificador
    aplicacion.config["reprogramar"] = reprogramar
    return planificador


# ------------------------------------------------- publicacion en internet --
class SesionSegunConexion(SecureCookieSessionInterface):
    """Cookie Secure solo cuando la peticion llega por https.

    Con la direccion publica https (tunel o servidor), quien entra en local por
    http://127.0.0.1 necesita una cookie sin Secure o no podria iniciar sesion.
    """

    def get_cookie_secure(self, app) -> bool:  # noqa: D102
        return request.is_secure


# Lo unico que se sirve a quien llega desde la direccion publica: los botones
# del correo (documentos con clave y descartes), sus estaticos y /salud.
RUTAS_PUBLICAS = ("/d/", "/descartar/", "/estaticos/", "/salud")
HOSTS_LOCALES = ("127.0.0.1", "localhost", "::1", "")


def _host_publico() -> str:
    from urllib.parse import urlparse

    from negocio import correo

    return (urlparse(correo.url_publica()).hostname or "").lower()


def es_peticion_publica() -> bool:
    """La peticion viene de internet (direccion publica o tunel de Tailscale)."""
    if request.headers.get("Tailscale-Funnel-Request"):
        return True
    publico = _host_publico()
    if publico in HOSTS_LOCALES:
        return False
    host = (request.headers.get("X-Forwarded-Host") or request.host or "").split(":")[0].lower()
    return host == publico


# ------------------------------------------------------------- aplicacion --
def crear_aplicacion() -> Flask:
    preparar_registro()
    registro.info("%s v%s - arrancando", config.NOMBRE_APP, config.VERSION)
    registro.info("Carpeta de datos: %s", config.DATOS)

    repositorio.aplicar_esquema()
    provisional = repositorio.asegurar_admin_inicial()
    if provisional:
        registro.warning("Usuario inicial 'admin' creado con clave provisional: %s", provisional)

    interrumpidas = repositorio.marcar_ejecuciones_interrumpidas()
    if interrumpidas:
        registro.warning("%s ejecucion(es) quedaron a medias y se marcan como interrumpidas",
                         interrumpidas)

    repositorio.limpiar_sesiones_caducadas()
    repositorio.limpiar_intentos_antiguos()
    repositorio.documentos_generando_huerfanos()
    from integraciones import anthropic_cliente
    if anthropic_cliente.corregir_clave_guardada():
        registro.warning("La clave de API estaba guardada duplicada: corregida")
    if "onedrive" in str(config.DATOS).lower():
        registro.warning("La carpeta de datos esta dentro de OneDrive (%s): la sincronizacion "
                         "puede corromper la base de datos y sube las claves cifradas a la nube",
                         config.DATOS)

    try:
        destino = copias.crear_copia("arranque")
        registro.info("Copia de seguridad de arranque: %s", destino.name)
    except Exception as error:  # noqa: BLE001 - una copia fallida no impide arrancar
        registro.error("No se pudo hacer la copia de arranque: %s", error)

    aplicacion = Flask(__name__,
                       template_folder=str(config.RUTA_PLANTILLAS),
                       static_folder=str(config.RUTA_ESTATICOS),
                       static_url_path="/estaticos")
    aplicacion.secret_key = secreto_persistente()
    aplicacion.session_interface = SesionSegunConexion()
    aplicacion.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="mova_boletines",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        clave_provisional=provisional,
    )
    aplicacion.register_blueprint(plano_web)
    if config.DETRAS_DE_PROXY:
        # Un solo salto (Nginx o el tunel): IP, esquema y host reales del visitante.
        aplicacion.wsgi_app = ProxyFix(aplicacion.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @aplicacion.after_request
    def cabeceras_seguridad(respuesta):
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        respuesta.headers.setdefault("Referrer-Policy", "same-origin")
        if request.is_secure:
            respuesta.headers.setdefault("Strict-Transport-Security",
                                         "max-age=31536000; includeSubDomains")
        return respuesta

    @aplicacion.before_request
    def solo_enlaces_desde_internet():
        """Desde internet solo responden los enlaces del correo.

        Panel, ajustes, usuarios e inicio de sesion no existen para quien llega
        por la direccion publica: se administran desde el propio equipo. Se
        puede desactivar con MOVA_PUBLICO_SOLO_ENLACES=0 (servidor con usuarios
        que entran desde fuera).
        """
        if not config.PUBLICO_SOLO_ENLACES or not es_peticion_publica():
            return None
        if request.path.startswith(RUTAS_PUBLICAS):
            return None
        return render_template(
            "descarte_ok.html", titulo_pagina="MOVA Boletines Oficiales",
            titulo_resultado="Direccion reservada", clase="warn",
            mensaje="Esta direccion solo sirve para abrir los botones de los correos "
                    "(resumenes, infografia y descartes).", publicacion=""), 404

    @aplicacion.teardown_appcontext
    def cerrar(_error=None):
        return None

    configurar_planificador(aplicacion)
    return aplicacion


def abrir_navegador(url: str) -> None:
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


# --------------------------------------------------------- instancia unica --
def ya_hay_instancia(host: str, puerto: int) -> tuple[bool, str]:
    """Comprueba si la herramienta ya esta corriendo en ese puerto.

    Es imprescindible con la tarea programada de Windows: la tarea se dispara
    al iniciar sesion y otra vez antes de la vigilancia, asi que puede intentar
    arrancar una segunda copia. Dos procesos sobre la misma base de datos se
    pisarian: el segundo marcaria como 'interrumpida' la ejecucion que el
    primero esta haciendo y ambos programarian la vigilancia del dia.
    """
    import urllib.error
    import urllib.request

    destino = "127.0.0.1" if host == "0.0.0.0" else host
    try:
        with socket.create_connection((destino, puerto), timeout=2):
            pass
    except OSError:
        return False, ""  # puerto libre: no hay nadie

    try:
        with urllib.request.urlopen(f"http://{destino}:{puerto}/salud", timeout=3) as respuesta:
            if respuesta.read(16).strip() == b"ok":
                return True, f"MOVA Boletines Oficiales ya esta en marcha en http://{destino}:{puerto}"
    except (urllib.error.URLError, OSError):
        pass
    return True, (f"El puerto {puerto} esta ocupado por otro programa. Cambia MOVA_PUERTO "
                  f"o para el programa que lo ocupa.")


def leer_argumentos(argumentos: list[str] | None = None):
    analizador = argparse.ArgumentParser(
        prog="MOVA Boletines Oficiales",
        description="Vigilancia diaria de ayudas y subvenciones en boletines autonomicos.")
    analizador.add_argument("--sin-navegador", action="store_true",
                            help="no abre el navegador al arrancar (tarea programada y servidor)")
    analizador.add_argument("--puerto", type=int, default=None,
                            help=f"puerto del servidor web (por defecto {config.PUERTO})")
    analizador.add_argument("--datos", default=None,
                            help="carpeta de datos alternativa (equivale a MOVA_DATOS)")
    return analizador.parse_args(argumentos)


def main(argumentos: list[str] | None = None) -> int:
    from waitress import serve

    opciones = leer_argumentos(argumentos)
    if opciones.datos:
        os.environ["MOVA_DATOS"] = opciones.datos
        importlib.reload(config)
    if opciones.puerto:
        config.PUERTO = opciones.puerto
    if opciones.sin_navegador:
        config.ABRIR_NAVEGADOR = False

    ocupado, motivo = ya_hay_instancia(config.HOST, config.PUERTO)
    if ocupado:
        # Salida 0 a proposito: para la tarea programada esto NO es un fallo,
        # significa que la herramienta ya estaba levantada.
        print(motivo)
        return 0

    aplicacion = crear_aplicacion()
    url = f"http://{'127.0.0.1' if config.HOST == '0.0.0.0' else config.HOST}:{config.PUERTO}"
    registro.info("Servidor en %s (un proceso, varios hilos)", url)

    if config.ABRIR_NAVEGADOR:
        abrir_navegador(url)

    # threads=8: suficiente para la interfaz mientras el pipeline usa su hilo.
    serve(aplicacion, host=config.HOST, port=config.PUERTO, threads=8,
          channel_timeout=600, ident="MOVA Boletines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
