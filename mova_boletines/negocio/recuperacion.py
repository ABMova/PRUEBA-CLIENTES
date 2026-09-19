"""Hace lo que no se hizo porque el equipo estaba apagado o dormido.

El planificador solo dispara a su hora: si a las 07:45 el equipo esta apagado,
ese dia no se vigila. Este modulo se ejecuta al arrancar y cada 10 minutos (lo
que cubre tambien la vuelta de la suspension) y recupera, del mas antiguo al
mas reciente:

  - la vigilancia de la manana de cada dia programado que no tenga una
    ejecucion buena, con la fecha de ESE dia (el correo lleva lo publicado ese
    dia, como si hubiera salido a su hora, y el asunto avisa del retraso);
  - la comprobacion de la tarde, si ninguna ejecucion de ese dia empezo
    despues de su hora (una recuperacion de la manana hecha por la noche ya la
    cubre, asi que no se duplica);
  - el resumen semanal de la semana en curso si aun no se envio.

Limites: como mucho `dias_recuperacion` dias hacia atras (7), nada anterior a
la primera vez que se activo esta funcion, 3 intentos fallidos por dia y tipo,
y no se lanza nada sin conexion a internet (al encender, la red tarda en
llegar: se espera al siguiente intento en vez de mandar un correo de fallos).
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

import config
from datos import repositorio
from negocio import orquestador

registro = logging.getLogger("mova")

MARGEN = timedelta(minutes=10)      # el planificador normal tiene prioridad a su hora
INTENTOS_MAX = 3
ESPERA_MAXIMA_EJECUCION_S = 3 * 3600
TIPO_MANANA = "recuperada"
TIPO_TARDE = "tarde_recuperada"
TIPOS_RECUPERADOS = (TIPO_MANANA, TIPO_TARDE)
_BUENOS = ("correcta", "con_avisos")
# Hosts de boletines vigilados: basta con que responda uno para dar la red por buena.
_PRUEBA_RED = (("dogv.gva.es", 443), ("www.bocm.es", 443), ("www.juntadeandalucia.es", 443))

_candado = threading.Lock()
_fallos_semanal: dict[str, int] = {}


def _zona() -> ZoneInfo:
    return ZoneInfo(repositorio.ajuste("zona_horaria", config.ZONA_HORARIA))


def _disparos(hora: str, dias: str, zona: ZoneInfo, desde: datetime,
              hasta: datetime) -> list[datetime]:
    """Horas a las que el planificador tendria que haber disparado entre dos momentos."""
    try:
        horas, minutos = (int(x) for x in hora.split(":"))
        disparo = CronTrigger(day_of_week=dias or "mon-fri", hour=horas, minute=minutos,
                              timezone=zona)
    except ValueError:
        return []
    resultado = []
    momento = disparo.get_next_fire_time(None, desde)
    while momento and momento <= hasta:
        resultado.append(momento)
        momento = disparo.get_next_fire_time(momento, momento + timedelta(seconds=1))
    return resultado


def _iniciada(fila, zona: ZoneInfo) -> datetime:
    # SQLite guarda datetime('now') en UTC.
    return (datetime.strptime(fila["iniciado_en"], "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=timezone.utc).astimezone(zona))


def _buena(fila) -> bool:
    """Cuenta como hecha: termino bien y consulto al menos un boletin, o se cancelo a mano."""
    if fila["estado"] == "cancelada":
        return True
    return fila["estado"] in _BUENOS and fila["boletines_ok"] > 0


def _activa() -> bool:
    return (repositorio.ajuste("planificador_activo", "1") == "1"
            and repositorio.ajuste("recuperacion_activa", "1") == "1")


def asegurar_punto_de_partida(ahora: datetime | None = None) -> None:
    """La primera vez no se recupera el pasado lejano: se parte de ayer.

    Sin esto, al instalar la funcion se lanzarian de golpe los ultimos 7 dias
    y el resumen semanal de una semana que ya paso.
    """
    ahora = ahora or datetime.now(_zona())
    if not repositorio.ajuste("recuperacion_desde"):
        repositorio.guardar_ajuste("recuperacion_desde",
                                   (ahora.date() - timedelta(days=1)).isoformat())
    if not repositorio.ajuste("semanal_ultima_semana"):
        repositorio.guardar_ajuste("semanal_ultima_semana", _lunes(ahora.date()).isoformat())


def _lunes(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def pendientes(ahora: datetime | None = None) -> list[tuple[date, str]]:
    """Vigilancias que tendrian que haberse hecho y no se hicieron, de la mas antigua."""
    if not _activa():
        return []
    zona = _zona()
    ahora = ahora or datetime.now(zona)
    dias_atras = max(1, repositorio.ajuste_int("dias_recuperacion", 7))
    desde = ahora - timedelta(days=dias_atras)
    try:
        punto = datetime.combine(date.fromisoformat(repositorio.ajuste("recuperacion_desde")),
                                 datetime.min.time(), zona)
        desde = max(desde, punto)
    except ValueError:
        pass
    hasta = ahora - MARGEN
    dias = repositorio.ajuste("dias_ejecucion", "mon-fri")

    tareas = [(d, TIPO_MANANA) for d in
              _disparos(repositorio.ajuste("hora_ejecucion", "07:45"), dias, zona, desde, hasta)]
    if repositorio.ajuste("tarde_activa", "1") == "1":
        tareas += [(d, TIPO_TARDE) for d in
                   _disparos(repositorio.ajuste("hora_tarde", "20:00"), dias, zona, desde, hasta)]
    tareas.sort()

    resultado = []
    for disparo, tipo in tareas:
        filas = repositorio.ejecuciones_de_fecha(disparo.date().isoformat())
        if any(f["estado"] == "en_curso" for f in filas):
            continue
        if tipo == TIPO_MANANA:
            hecha = any(_buena(f) for f in filas)
        else:
            hecha = any(_buena(f) and _iniciada(f, zona) >= disparo for f in filas)
        if hecha:
            continue
        fallidas = sum(1 for f in filas if f["tipo"] == tipo and not _buena(f))
        if fallidas >= INTENTOS_MAX:
            continue
        resultado.append((disparo.date(), tipo))
    return resultado


def semanal_pendiente(ahora: datetime | None = None) -> date | None:
    """Lunes de la semana cuyo resumen falta por enviar, o None."""
    if not _activa() or repositorio.ajuste("semanal_activo", "1") != "1":
        return None
    zona = _zona()
    ahora = ahora or datetime.now(zona)
    disparos = _disparos(repositorio.ajuste("hora_semanal", "08:30"),
                         repositorio.ajuste("dia_semanal", "mon"), zona,
                         ahora - timedelta(days=7), ahora - MARGEN)
    if not disparos:
        return None
    semana = _lunes(disparos[-1].date())
    if repositorio.ajuste("semanal_ultima_semana") >= semana.isoformat():
        return None
    if _fallos_semanal.get(semana.isoformat(), 0) >= INTENTOS_MAX:
        return None
    return semana


def hay_internet() -> bool:
    for destino in _PRUEBA_RED:
        try:
            with socket.create_connection(destino, timeout=5):
                return True
        except OSError:
            continue
    return False


def _esperar_fin() -> None:
    limite = time.monotonic() + ESPERA_MAXIMA_EJECUCION_S
    while orquestador.hay_ejecucion() and time.monotonic() < limite:
        time.sleep(5)


def recuperar(comprobar_red=hay_internet) -> list[str]:
    """Lanza, una detras de otra, las vigilancias pendientes. Devuelve lo hecho."""
    if not _candado.acquire(blocking=False):
        return []
    hecho: list[str] = []
    try:
        if not _activa():
            return hecho
        asegurar_punto_de_partida()
        for _ in range(4 * max(1, repositorio.ajuste_int("dias_recuperacion", 7))):
            lista = pendientes()
            if not lista or orquestador.hay_ejecucion():
                break
            if not comprobar_red():
                registro.info("Hay %d vigilancia(s) pendiente(s), pero aun no hay conexion; "
                              "se reintenta en unos minutos", len(lista))
                return hecho
            fecha, tipo = lista[0]
            nombre = "comprobacion de la tarde" if tipo == TIPO_TARDE else "vigilancia"
            aceptada, mensaje = orquestador.lanzar(fecha, tipo, "recuperacion")
            registro.info("Recuperando la %s del %s (el equipo no estaba encendido): %s",
                          nombre, f"{fecha:%d/%m/%Y}", mensaje)
            if not aceptada:
                break
            hecho.append(f"{tipo} {fecha.isoformat()}")
            _esperar_fin()

        semana = semanal_pendiente()
        if semana and not orquestador.hay_ejecucion() and comprobar_red():
            exito, detalle = orquestador.enviar_resumen_semanal(usuario="recuperacion")
            registro.info("Resumen semanal recuperado: %s", detalle)
            if exito:
                hecho.append(f"semanal {semana.isoformat()}")
            else:
                clave = semana.isoformat()
                _fallos_semanal[clave] = _fallos_semanal.get(clave, 0) + 1
        return hecho
    finally:
        repositorio.cerrar_conexion()
        _candado.release()
