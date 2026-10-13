"""Roles y control de acceso. El usuario se relee de la base en cada petición:
desactivar a alguien lo deja fuera al instante."""
from functools import wraps

from flask import abort, g, redirect, request, session, url_for

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
    return bool(u) and u["rol"] in PERMISOS.get(permiso, set())


def cargar_usuario() -> None:
    g.usuario = None
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
                abort(403)
            return f(*a, **kw)
        return envoltura
    return deco
