"""Administración: usuarios, auditoría, copias de seguridad y configuración."""
import io
import secrets
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

import config
from auth import user
from auth.permissions import ROLES, requiere
from integrations import claude_api, web_scraper
from logic import parser
from models import db
from routes import orquestador

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _auditar(accion, entidad, detalle=None):
    db.auditar(g.usuario["id"], g.usuario["email"], accion, entidad, detalle, g.ip)


# ---------------------------------------------------------------- usuarios
@bp.route("/usuarios", methods=["GET", "POST"])
@requiere("administrar")
def usuarios():
    clave_nueva = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        nombre = request.form.get("nombre", "").strip()
        rol = request.form.get("rol", "consultor")
        if not email or "@" not in email or not nombre or rol not in ROLES:
            flash("Indique nombre, correo y rol.", "err")
        elif db.usuario_por_email(email):
            flash("Ya existe un usuario con ese correo.", "err")
        else:
            clave_nueva = secrets.token_urlsafe(9)
            uid = db.crear_usuario(email, nombre, user.hash_clave(clave_nueva), rol, cambiar_clave=1)
            _auditar("alta_usuario", f"usuario:{uid}", {"email": email, "rol": rol})
            flash(f"Usuario creado. Contraseña provisional para {email} (se muestra una sola vez):", "ok")
    return render_template("admin/usuarios.html", usuarios=db.listar_usuarios(), clave_nueva=clave_nueva)


@bp.route("/usuarios/<int:uid>", methods=["POST"])
@requiere("administrar")
def editar_usuario(uid):
    u = db.usuario_por_id(uid) or abort(404)
    accion = request.form.get("accion")
    if accion == "rol":
        rol = request.form.get("rol")
        if rol not in ROLES:
            abort(400)
        if u["rol"] == "admin" and rol != "admin" and db.contar_admins_activos() <= 1:
            flash("Debe quedar al menos un administrador activo.", "err")
        else:
            db.actualizar_usuario(uid, rol=rol)
            _auditar("modificacion_usuario", f"usuario:{uid}", {"rol": [u["rol"], rol]})
            flash("Rol actualizado.", "ok")
    elif accion == "activar":
        activo = 0 if u["activo"] else 1
        if not activo and u["rol"] == "admin" and db.contar_admins_activos() <= 1:
            flash("Debe quedar al menos un administrador activo.", "err")
        elif uid == g.usuario["id"] and not activo:
            flash("No puede desactivar su propio usuario.", "err")
        else:
            db.actualizar_usuario(uid, activo=activo)
            _auditar("modificacion_usuario", f"usuario:{uid}", {"activo": activo})
            flash("Usuario " + ("activado." if activo else "desactivado: queda fuera desde ya."), "ok")
    elif accion == "restablecer":
        clave = secrets.token_urlsafe(9)
        db.actualizar_usuario(uid, contrasena_hash=user.hash_clave(clave), cambiar_clave=1)
        _auditar("restablecer_clave", f"usuario:{uid}", {"email": u["email"]})
        flash(f"Contraseña provisional de {u['email']} (se muestra una sola vez): {clave}", "ok")
    return redirect(url_for("admin.usuarios"))


# ---------------------------------------------------------------- auditoría
@bp.route("/auditoria")
@requiere("administrar")
def auditoria():
    filtros = {"usuario_id": request.args.get("usuario", type=int), "accion": request.args.get("accion") or None,
               "texto": request.args.get("q", "").strip() or None}
    return render_template("admin/auditoria.html", registros=db.listar_auditoria(500, **filtros),
                           usuarios=db.listar_usuarios(), acciones=db.acciones_auditadas(), filtros=filtros)


# ---------------------------------------------------------------- copias de seguridad
@bp.route("/backups")
@requiere("administrar")
def backups():
    return render_template("admin/backups.html", copias=db.listar_copias(), datos=config.DATOS)


@bp.route("/backups/ahora", methods=["POST"])
@requiere("administrar")
def copia_ahora():
    ruta = db.copia_automatica()
    _auditar("copia_seguridad", "base_datos", {"fichero": ruta.name})
    flash(f"Copia creada: {ruta.name}", "ok")
    return redirect(url_for("admin.backups"))


@bp.route("/backups/descargar")
@requiere("administrar")
def descargar_backup():
    nombre = f"mova_minimis_copia_{datetime.now():%Y%m%d_%H%M%S}.zip"
    with tempfile.TemporaryDirectory(dir=config.DATOS) as tmp:  # no se queda ningún .zip en el disco
        ruta = db.crear_zip_copia(Path(tmp) / nombre)
        contenido = io.BytesIO(ruta.read_bytes())
    _auditar("descarga_copia", "base_datos", {"fichero": nombre, "bytes": contenido.getbuffer().nbytes})
    return send_file(contenido, as_attachment=True, download_name=nombre, mimetype="application/zip")


@bp.route("/backups/restaurar", methods=["POST"])
@requiere("administrar")
def restaurar():
    f = request.files.get("copia")
    if not f or not f.filename:
        flash("Elija un fichero .zip o .db.", "err")
        return redirect(url_for("admin.backups"))
    with tempfile.TemporaryDirectory(dir=config.DATOS) as tmp:
        tmp = Path(tmp)
        subido = tmp / Path(f.filename).name
        f.save(subido)
        zf = None
        if subido.suffix.lower() == ".zip":
            try:
                zf = zipfile.ZipFile(subido)
                if "minimis.db" not in zf.namelist():
                    raise zipfile.BadZipFile
                with zf.open("minimis.db") as src, open(tmp / "minimis.db", "wb") as dst:
                    dst.write(src.read())
                db_origen = tmp / "minimis.db"
            except zipfile.BadZipFile:
                flash("El .zip no es una copia de MOVA Minimis (falta minimis.db).", "err")
                return redirect(url_for("admin.backups"))
        else:
            db_origen = subido
        ok, motivo = db.comprobar_integridad(db_origen)
        if not ok:
            flash(motivo, "err")
            if zf:
                zf.close()
            return redirect(url_for("admin.backups"))
        try:
            previa = db.restaurar(db_origen, zf)
        except ValueError as e:
            flash(str(e), "err")
            return redirect(url_for("admin.backups"))
        finally:
            if zf:
                zf.close()
    # La auditoría restaurada no tiene este evento: se anota en la base ya restaurada
    _auditar("restauracion", "base_datos", {"origen": f.filename, "copia_previa": previa.name})
    flash(f"Copia restaurada. El estado anterior quedó guardado en {previa.name}. "
          "Si su usuario no existía en la copia, vuelva a entrar.", "ok")
    return redirect(url_for("admin.backups"))


@bp.route("/apagar", methods=["POST"])
@requiere("administrar")
def apagar():
    """El .exe no tiene ventana: esta es la forma limpia de pararlo."""
    import os
    import threading
    _auditar("apagado", "aplicacion")
    threading.Timer(1.0, os._exit, args=(0,)).start()
    return render_template("error.html", codigo="", titulo="Aplicación cerrada",
                           detalle="MOVA Minimis se ha detenido. Para volver a usarla, abra de nuevo el ejecutable.")


# ---------------------------------------------------------------- configuración
@bp.route("/configuracion", methods=["GET", "POST"])
@requiere("administrar")
def configuracion():
    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "guardar":
            modelo = request.form.get("modelo")
            if modelo in config.MODELOS_CLAUDE:
                db.guardar_ajuste("modelo_parser", modelo)
            modo = request.form.get("modo_periodo")
            if modo in ("movil", "ejercicios"):
                db.guardar_ajuste("modo_periodo", modo)
            clave = request.form.get("api_key", "").strip()
            cambios = {"modelo": modelo, "modo_periodo": modo}
            if clave:
                db.guardar_ajuste("anthropic_api_key", user.cifrar(clave))
                cambios["api_key"] = user.enmascarar(clave)
            _auditar("configuracion", "ajustes", cambios)
            flash("Configuración guardada.", "ok")
        elif accion == "borrar_clave":
            db.guardar_ajuste("anthropic_api_key", None)
            _auditar("configuracion", "ajustes", {"api_key": "borrada"})
            flash("Clave de Claude eliminada.", "ok")
        elif accion == "probar_bdns":
            try:
                n = len(web_scraper.buscar_beneficiarios("A46103834"))
                flash(f"BDNS operativa: responde la búsqueda de beneficiarios ({n} registro).", "ok")
            except web_scraper.ErrorBDNS as e:
                flash(f"La BDNS no responde: {e}", "err")
        elif accion == "probar_claude":
            clave = orquestador.clave_claude()
            if not clave:
                flash("No hay clave de Claude configurada.", "err")
            else:
                try:
                    datos, uso = claude_api.llamar_json(
                        clave, orquestador.modelo_claude(), "Responde solo con el JSON pedido.",
                        [{"type": "text", "text": "Devuelve ok=true."}],
                        {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
                         "additionalProperties": False}, max_tokens=200)
                    flash(f"Claude responde ({uso['modelo']}, {uso['entrada']}+{uso['salida']} tokens).", "ok")
                except claude_api.ErrorClaude as e:
                    flash(str(e), "err")
        elif accion == "vaciar_cache":
            n = db.vaciar_cache()
            _auditar("configuracion", "cache_bdns", {"borradas": n})
            flash(f"Caché de la BDNS vaciada ({n} entradas).", "ok")
        return redirect(url_for("admin.configuracion"))
    clave = orquestador.clave_claude()
    origen_clave = "base de datos (cifrada)" if db.leer_ajuste("anthropic_api_key") else (
        ".env (ANTHROPIC_API_KEY)" if clave else None)
    return render_template("admin/configuracion.html", modelos=config.MODELOS_CLAUDE,
                           modelo=orquestador.modelo_claude(), clave_mascara=user.enmascarar(clave),
                           origen_clave=origen_clave, modo=db.leer_ajuste("modo_periodo", "movil"),
                           tesseract=parser.tesseract_disponible(), datos=config.DATOS, version=config.VERSION,
                           bdns=config.BDNS_API)
