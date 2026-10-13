"""Acceso: entrar, salir y cambiar la contraseña."""
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from auth import user
from auth.permissions import requiere
from models import db

bp = Blueprint("auth", __name__)

_fallos: dict[tuple[str, str], deque] = defaultdict(deque)
MAX_FALLOS, VENTANA_S = 8, 15 * 60


def _bloqueado(clave: tuple[str, str]) -> bool:
    """Por IP y correo: en el equipo todos entran desde 127.0.0.1 y no deben bloquearse entre sí."""
    q = _fallos[clave]
    while q and time.time() - q[0] > VENTANA_S:
        q.popleft()
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
    if g.get("usuario"):
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
        _fallos[clave_fallos].append(time.time())
        db.auditar(u["id"] if u else None, email or None, "login_fallido", "usuario",
                   {"motivo": "usuario desactivado" if u and not u["activo"] else "credenciales"}, g.ip)
        flash("Correo o contraseña incorrectos.", "err")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if g.get("usuario"):
        db.auditar(g.usuario["id"], g.usuario["email"], "logout", "usuario", None, g.ip)
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/cambiar-clave", methods=["GET", "POST"])
@requiere("ver")
def cambiar_clave():
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
