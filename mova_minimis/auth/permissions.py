"""Roles y control de acceso. El usuario se relee de la base en cada petición:
desactivar a alguien lo deja fuera al instante."""
import os
import secrets
import time
from functools import wraps

from flask import abort, g, redirect, request, session, url_for

import config
from models import db

ROLES = {
    "admin": "Administrador",
    "consultor": "Consultor",
    "viewer": "Solo lectura",
}

PERMISOS = {
    "consultar": {"admin", "consultor"},         # crear consultas, subir documentos
    "exportar": {"admin", "consultor"},          # generar informes
    "editar_resultados": {"admin", "consultor"}, # añadir ayudas declaradas
    "ver": {"admin", "consultor", "viewer"},
    "administrar": {"admin"},                    # usuarios, auditoría, copias, configuración
}


def puede(permiso: str, usuario=None) -> bool:
    u = usuario if usuario is not None else g.get("usuario")
    if not u or u["rol"] not in PERMISOS.get(permiso, set()):
        return False
    if config.ESCRITORIO and permiso == "administrar":
        return configuracion_desbloqueada()
    return True


# ---------------------------------------------------------------- modo escritorio
def configuracion_desbloqueada() -> bool:
    return session.get("config_hasta", 0) > time.time()


def desbloquear_configuracion() -> None:
    session["config_hasta"] = time.time() + config.MINUTOS_DESBLOQUEO * 60


def bloquear_configuracion() -> None:
    session.pop("config_hasta", None)


def nombre_de_windows() -> str:
    """'MOVA  Antonio Bastidas' -> 'Antonio Bastidas'. Si Windows no da nombre visible, el usuario."""
    nombre = ""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            n = wintypes.ULONG(256)
            b = ctypes.create_unicode_buffer(256)
            if ctypes.windll.secur32.GetUserNameExW(3, b, ctypes.byref(n)):  # 3 = NameDisplay
                nombre = " ".join(b.value.split())
        except (OSError, AttributeError):
            pass
    palabras = nombre.split()
    if len(palabras) > 2 and palabras[0].upper() == "MOVA":
        nombre = " ".join(palabras[1:])
    return nombre or os.environ.get("USERNAME") or "Usuario del equipo"


def usuario_del_equipo():
    """El único usuario de la versión de escritorio: la cuenta de Windows que la abre."""
    from auth import user
    u = db.usuario_por_email(config.EMAIL_ESCRITORIO)
    nombre = nombre_de_windows()
    if not u:
        # Contraseña aleatoria que nadie conoce: este usuario no entra por /login
        db.crear_usuario(config.EMAIL_ESCRITORIO, nombre, user.hash_clave(secrets.token_urlsafe(32)), "admin",
                         cambiar_clave=0)
        u = db.usuario_por_email(config.EMAIL_ESCRITORIO)
    elif u["nombre"] != nombre or not u["activo"] or u["rol"] != "admin":
        db.actualizar_usuario(u["id"], nombre=nombre, activo=1, rol="admin", cambiar_clave=0)
        u = db.usuario_por_email(config.EMAIL_ESCRITORIO)
    return u


def cargar_usuario() -> None:
    g.usuario = None
    if config.ESCRITORIO:
        g.usuario = usuario_del_equipo()
        session["uid"] = g.usuario["id"]
        if configuracion_desbloqueada():  # el desbloqueo se alarga mientras se usa
            desbloquear_configuracion()
        return
    uid = session.get("uid")
    if not uid:
        return
    u = db.usuario_por_id(uid)
    if not u or not u["activo"] or session.get("ver") != u["contrasena_hash"][-12:]:
        session.clear()  # desactivado o contraseña cambiada en otra sesión
        return
    g.usuario = u


def requiere(permiso: str = "ver"):
    def deco(f):
        @wraps(f)
        def envoltura(*a, **kw):
            if not g.get("usuario"):
                if request.path.startswith("/api/"):
                    abort(401)
                return redirect(url_for("auth.login", next=request.path))
            if g.usuario["cambiar_clave"] and request.endpoint not in ("auth.cambiar_clave", "auth.logout"):
                return redirect(url_for("auth.cambiar_clave"))
            if not puede(permiso):
                if config.ESCRITORIO and permiso == "administrar" and not request.path.startswith("/api/"):
                    return redirect(url_for("auth.desbloquear", next=request.path))
                abort(403)
            return f(*a, **kw)
        return envoltura
    return deco
