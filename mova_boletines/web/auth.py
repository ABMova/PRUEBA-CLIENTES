"""Autenticacion y permisos, en un unico sitio.

Los permisos se comprueban en CADA peticion (no solo al iniciar sesion):
cada decorador vuelve a leer la sesion y el rol vigente en base de datos.
"""
from __future__ import annotations

from functools import wraps

from flask import g, redirect, request, session, url_for

from datos import repositorio

COOKIE = "mova_sesion"

# Que puede hacer cada rol. La comprobacion es por permiso, no por rol suelto.
PERMISOS = {
    "administrador": {"ver", "ejecutar", "descartar", "editar", "administrar"},
    "editor": {"ver", "ejecutar", "descartar", "editar"},
    "consulta": {"ver"},
}

DESCRIPCION_ROLES = {
    "administrador": "Todo, incluidos usuarios, ajustes y copias",
    "editor": "Lanzar ejecuciones, descartar y editar palabras y destinatarios",
    "consulta": "Solo consultar",
}


def usuario_actual():
    """Lee la sesion y devuelve la fila de usuario vigente, o None."""
    if "usuario" in g:
        return g.usuario
    identificador = session.get(COOKIE, "")
    fila = repositorio.sesion_valida(identificador) if identificador else None
    g.usuario = fila
    return fila


def tiene_permiso(permiso: str) -> bool:
    fila = usuario_actual()
    if fila is None:
        return False
    return permiso in PERMISOS.get(fila["rol"], set())


# Freno a quien prueba contrasenas: por IP y por usuario, en una ventana movil.
MAX_FALLOS_IP = 10
MAX_FALLOS_USUARIO = 5
VENTANA_FALLOS = 15  # minutos
MENSAJE_BLOQUEO = ("Demasiados intentos fallidos. Por seguridad, espera 15 minutos antes de "
                   "volver a intentarlo.")


def _registrar_fallo(usuario: str, ip: str, motivo: str) -> None:
    repositorio.registrar_intento_ip(ip, "login_ip")
    repositorio.registrar_intento_ip(ip, f"login_usuario:{usuario.strip().lower()}")
    repositorio.registrar_auditoria(usuario, "inicio_sesion", usuario, motivo, ip, "error")


def iniciar_sesion(usuario: str, clave: str, ip: str, agente: str) -> tuple[bool, str]:
    nombre = usuario.strip().lower()
    if (repositorio.intentos_recientes(ip, VENTANA_FALLOS, "login_ip") >= MAX_FALLOS_IP
            or repositorio.intentos_de_recurso(f"login_usuario:{nombre}", VENTANA_FALLOS)
            >= MAX_FALLOS_USUARIO):
        repositorio.registrar_auditoria(usuario, "inicio_sesion", usuario,
                                        "Bloqueado por demasiados intentos fallidos", ip, "error")
        return False, MENSAJE_BLOQUEO

    fila = repositorio.usuario_por_nombre(usuario)
    if fila is None or not fila["activo"]:
        _registrar_fallo(usuario, ip, "Usuario inexistente o desactivado")
        return False, "Usuario o contrasena incorrectos"
    if not repositorio.verificar_clave(fila, clave):
        _registrar_fallo(usuario, ip, "Contrasena incorrecta")
        return False, "Usuario o contrasena incorrectos"

    identificador = repositorio.crear_sesion(fila["id"], ip, agente)
    session[COOKIE] = identificador
    session.permanent = True
    repositorio.marcar_acceso(fila["id"])
    repositorio.registrar_auditoria(fila["usuario"], "inicio_sesion", fila["usuario"],
                                    "Acceso correcto", ip)
    return True, "Sesion iniciada"


def cerrar_sesion(ip: str = "") -> None:
    identificador = session.get(COOKIE, "")
    fila = repositorio.sesion_valida(identificador) if identificador else None
    if identificador:
        repositorio.cerrar_sesion(identificador)
    if fila:
        repositorio.registrar_auditoria(fila["usuario"], "cierre_sesion", fila["usuario"], "", ip)
    session.clear()
    g.pop("usuario", None)


def requiere(permiso: str = "ver"):
    """Decorador de ruta: sesion valida + permiso + cambio de clave pendiente."""

    def envoltorio(funcion):
        @wraps(funcion)
        def interna(*args, **kwargs):
            fila = usuario_actual()
            if fila is None:
                return redirect(url_for("web.login", siguiente=request.path))
            if fila["cambio_obligatorio"] and request.endpoint not in (
                    "web.cambiar_clave", "web.salir"):
                return redirect(url_for("web.cambiar_clave"))
            if not tiene_permiso(permiso):
                repositorio.registrar_auditoria(
                    fila["usuario"], "acceso_denegado", request.path,
                    f"Se requiere permiso {permiso}", request.remote_addr or "", "error")
                return redirect(url_for("web.panel", aviso="sin_permiso"))
            return funcion(*args, **kwargs)

        return interna

    return envoltorio


def ip_peticion() -> str:
    """IP del visitante. Con MOVA_DETRAS_DE_PROXY=1 la corrige ProxyFix en app.py;
    sin proxy NO se lee X-Forwarded-For, que cualquiera puede inventarse."""
    return request.remote_addr or ""
