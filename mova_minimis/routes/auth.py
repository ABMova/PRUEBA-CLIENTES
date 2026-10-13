"""Acceso: entrar, salir y cambiar la contraseña."""
import time
from collections import deque
from urllib.parse import urlsplit

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

import config
from auth import permissions, user
from auth.permissions import requiere
from models import db

bp = Blueprint("auth", __name__)

_fallos: dict[tuple[str, str], deque] = {}
MAX_FALLOS, VENTANA_S = 8, 15 * 60


def _bloqueado(clave: tuple[str, str]) -> bool:
    """Por IP y correo: en el equipo todos entran desde 127.0.0.1 y no deben bloquearse entre sí."""
    q = _fallos.get(clave)
    if q is None:
        return False
    while q and time.time() - q[0] > VENTANA_S:
        q.popleft()
    if not q:
        del _fallos[clave]  # que el diccionario no crezca con cada correo tecleado
        return False
    return len(q) >= MAX_FALLOS


def _destino_seguro(nxt: str | None) -> str:
    """Solo rutas internas. Los navegadores leen la barra invertida como "/", así que "/" + "\\" + "dominio"
    acabaría en otro sitio: se rechaza cualquier barra invertida."""
    if not nxt or "\\" in nxt or not nxt.startswith("/") or nxt.startswith("//"):
        return url_for("dashboard.inicio")
    partes = urlsplit(nxt)
    return nxt if not partes.scheme and not partes.netloc else url_for("dashboard.inicio")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("usuario") or config.ESCRITORIO:
        return redirect(url_for("dashboard.inicio"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        clave_fallos = (g.ip, email)
        if _bloqueado(clave_fallos):
            flash("Demasiados intentos fallidos. Espere unos minutos.", "err")
            return render_template("login.html"), 429
        u = db.usuario_por_email(email) if email else None
        if u and u["activo"] and user.verificar_clave(request.form.get("clave", ""), u["contrasena_hash"]):
            csrf = session.get("csrf")
            session.clear()
            session.permanent = True
            session.update(uid=u["id"], ver=u["contrasena_hash"][-12:], csrf=csrf)
            db.actualizar_usuario(u["id"], ultimo_acceso=db.ahora_iso())
            db.auditar(u["id"], u["email"], "login", "usuario", None, g.ip)
            _fallos.pop(clave_fallos, None)
            if u["cambiar_clave"]:
                return redirect(url_for("auth.cambiar_clave"))
            return redirect(_destino_seguro(request.args.get("next")))
        _fallos.setdefault(clave_fallos, deque()).append(time.time())
        if len(_fallos) > 1000:  # barrido de lo caducado para que no crezca sin fin
            for k in [k for k, q in _fallos.items() if time.time() - q[-1] > VENTANA_S]:
                del _fallos[k]
        db.auditar(u["id"] if u else None, email or None, "login_fallido", "usuario",
                   {"motivo": "usuario desactivado" if u and not u["activo"] else "credenciales"}, g.ip)
        flash("Correo o contraseña incorrectos.", "err")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if config.ESCRITORIO:
        permissions.bloquear_configuracion()
        return redirect(url_for("dashboard.inicio"))
    if g.get("usuario"):
        db.auditar(g.usuario["id"], g.usuario["email"], "logout", "usuario", None, g.ip)
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/cambiar-clave", methods=["GET", "POST"])
@requiere("ver")
def cambiar_clave():
    if config.ESCRITORIO:
        return redirect(url_for("admin.configuracion") + "#clave-config")
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        if not user.verificar_clave(actual, g.usuario["contrasena_hash"]):
            flash("La contraseña actual no es correcta.", "err")
        elif nueva != request.form.get("repetir", ""):
            flash("Las dos contraseñas nuevas no coinciden.", "err")
        elif problemas := user.problemas_clave(nueva):
            flash("La contraseña nueva necesita " + ", ".join(problemas) + ".", "err")
        else:
            h = user.hash_clave(nueva)
            db.actualizar_usuario(g.usuario["id"], contrasena_hash=h, cambiar_clave=0)
            session["ver"] = h[-12:]
            db.auditar(g.usuario["id"], g.usuario["email"], "cambio_clave", "usuario", None, g.ip)
            flash("Contraseña actualizada.", "ok")
            return redirect(url_for("dashboard.inicio"))
    return render_template("cambiar_clave.html", obligatorio=bool(g.usuario["cambiar_clave"]))


# ---------------------------------------------------------------- escritorio: candado de la configuración
CLAVE_CONFIG = "clave_configuracion"


@bp.route("/desbloquear", methods=["GET", "POST"])
def desbloquear():
    """Escritorio: la administración pide una contraseña propia. La primera vez se crea aquí."""
    if not config.ESCRITORIO:
        return redirect(url_for("admin.configuracion"))
    siguiente = _destino_seguro(request.args.get("next") or url_for("admin.configuracion"))
    guardada = db.leer_ajuste(CLAVE_CONFIG)
    clave_fallos = (g.ip, "configuracion")
    if request.method == "POST":
        clave = request.form.get("clave", "")
        if _bloqueado(clave_fallos):
            flash("Demasiados intentos fallidos. Espera unos minutos.", "err")
        elif not guardada:
            if clave != request.form.get("repetir", ""):
                flash("Las dos contraseñas no coinciden.", "err")
            elif problemas := user.problemas_clave(clave):
                flash("La contraseña necesita " + ", ".join(problemas) + ".", "err")
            else:
                db.guardar_ajuste(CLAVE_CONFIG, user.hash_clave(clave))
                permissions.desbloquear_configuracion()
                db.auditar(g.usuario["id"], g.usuario["email"], "clave_configuracion_creada", "configuracion", None, g.ip)
                flash("Contraseña de configuración creada. Guárdala: sin ella no se puede entrar en la administración.", "ok")
                return redirect(siguiente)
        elif user.verificar_clave(clave, guardada):
            _fallos.pop(clave_fallos, None)
            permissions.desbloquear_configuracion()
            db.auditar(g.usuario["id"], g.usuario["email"], "desbloqueo_configuracion", "configuracion", None, g.ip)
            return redirect(siguiente)
        else:
            _fallos.setdefault(clave_fallos, deque()).append(time.time())
            db.auditar(g.usuario["id"], g.usuario["email"], "desbloqueo_fallido", "configuracion", None, g.ip)
            flash("Contraseña incorrecta.", "err")
    return render_template("desbloquear.html", crear=not guardada, siguiente=siguiente,
                           minutos=config.MINUTOS_DESBLOQUEO)


@bp.route("/bloquear", methods=["POST"])
def bloquear():
    permissions.bloquear_configuracion()
    flash("Administración bloqueada.", "ok")
    return redirect(url_for("dashboard.inicio"))
