"""Arranque de MOVA Boletines Oficiales.

IMPORTANTE: un solo proceso con varios hilos. El progreso de la ejecucion vive
en memoria, asi que con varios workers la interfaz veria estados distintos.
"""
from __future__ import annotations

import logging
import logging.handlers
import secrets
import sys
import threading
import webbrowser
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask

import config
from datos import copias, repositorio
from negocio import orquestador
from web.rutas import web as plano_web

registro = logging.getLogger("mova")


# ------------------------------------------------------------------ registro --
def preparar_registro() -> None:
    config.preparar_carpetas()
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


def configurar_planificador(aplicacion: Flask) -> BackgroundScheduler:
    planificador = BackgroundScheduler(timezone=repositorio.ajuste("zona_horaria",
                                                                   config.ZONA_HORARIA))
    planificador.start()

    def reprogramar() -> None:
        planificador.remove_all_jobs()
        hora = repositorio.ajuste("hora_ejecucion", "07:45")
        dias = repositorio.ajuste("dias_ejecucion", "mon-fri")
        try:
            horas, minutos = hora.split(":")
            disparo = CronTrigger(day_of_week=dias, hour=int(horas), minute=int(minutos),
                                  timezone=repositorio.ajuste("zona_horaria", config.ZONA_HORARIA))
        except ValueError:
            registro.error("Horario no valido (%s %s); se usa 07:45 mon-fri", hora, dias)
            disparo = CronTrigger(day_of_week="mon-fri", hour=7, minute=45,
                                  timezone=config.ZONA_HORARIA)
        planificador.add_job(_tarea_programada, disparo, id="vigilancia_diaria",
                             replace_existing=True, misfire_grace_time=3600,
                             coalesce=True, max_instances=1)
        trabajos = planificador.get_jobs()
        if trabajos and trabajos[0].next_run_time:
            registro.info("Proxima vigilancia: %s",
                          trabajos[0].next_run_time.strftime("%d/%m/%Y %H:%M %Z"))

    reprogramar()
    aplicacion.config["planificador"] = planificador
    aplicacion.config["reprogramar"] = reprogramar
    return planificador


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
    aplicacion.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="mova_boletines",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        clave_provisional=provisional,
    )
    aplicacion.register_blueprint(plano_web)

    @aplicacion.after_request
    def cabeceras_seguridad(respuesta):
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        respuesta.headers.setdefault("Referrer-Policy", "same-origin")
        return respuesta

    @aplicacion.teardown_appcontext
    def cerrar(_error=None):
        return None

    configurar_planificador(aplicacion)
    return aplicacion


def abrir_navegador(url: str) -> None:
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


def main() -> None:
    from waitress import serve

    aplicacion = crear_aplicacion()
    url = f"http://{'127.0.0.1' if config.HOST == '0.0.0.0' else config.HOST}:{config.PUERTO}"
    registro.info("Servidor en %s (un proceso, varios hilos)", url)

    if config.ABRIR_NAVEGADOR:
        abrir_navegador(url)

    # threads=8: suficiente para la interfaz mientras el pipeline usa su hilo.
    serve(aplicacion, host=config.HOST, port=config.PUERTO, threads=8,
          channel_timeout=600, ident="MOVA Boletines")


if __name__ == "__main__":
    main()
