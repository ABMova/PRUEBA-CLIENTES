"""Crear consultas: subir documentos, entrada manual, lanzar, seguir y cancelar."""
import hashlib
import json
import logging
import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

import config
from auth import user
from auth.permissions import requiere
from integrations.claude_api import ErrorClaude
from logic import parser
from models import db
from routes import orquestador

bp = Blueprint("consultas", __name__)
log = logging.getLogger(__name__)


def _numero(valor, defecto: float) -> float:
    try:
        return min(max(float(valor), 0.0), 1.0)
    except (TypeError, ValueError):
        return defecto


def _anos_por_defecto() -> list[int]:
    hoy = date.today()
    return [hoy.year - 3, hoy.year - 2, hoy.year - 1]  # últimos tres ejercicios completos


@bp.route("/consultas/nueva")
@requiere("consultar")
def nueva():
    return render_template("consulta_nueva.html", hoy=date.today().isoformat(), anos_defecto=_anos_por_defecto(),
                           modo_defecto=db.leer_ajuste("modo_periodo", "movil"),
                           hay_claude=bool(orquestador.clave_claude()), hay_ocr=bool(parser.tesseract_disponible()),
                           extensiones=", ".join(sorted(parser.EXTENSIONES)))


@bp.route("/api/documentos", methods=["POST"])
@requiere("consultar")
def subir_documentos():
    ficheros = request.files.getlist("ficheros")
    if not ficheros:
        return jsonify({"error": "No se recibió ningún fichero."}), 400
    salidas, docs, avisos_claude = [], [], []
    tmp_dir = config.DIR_TEMPORAL
    llamar = orquestador.llamador_claude(aviso=avisos_claude.append)
    for f in ficheros:
        nombre = Path(f.filename or "documento").name
        ext = Path(nombre).suffix.lower()
        if ext not in parser.EXTENSIONES:
            salidas.append({"clientes": [], "errores": [{"entrada": nombre, "error": "tipo de fichero no admitido"}]})
            continue
        datos = f.read()
        if len(datos) > config.MAX_SUBIDA_MB * 1024 * 1024:
            salidas.append({"clientes": [], "errores": [
                {"entrada": nombre, "error": f"supera {config.MAX_SUBIDA_MB} MB"}]})
            continue
        huella = hashlib.sha256(datos).hexdigest()
        tmp = tmp_dir / f"{huella}{ext}"
        tmp.write_bytes(datos)
        try:
            salida = parser.procesar_documento(tmp, nombre, llamar_claude=llamar, aviso=avisos_claude.append)
        except ErrorClaude as e:
            salida = {"clientes": [], "errores": [{"entrada": nombre, "error": str(e)}], "avisos": [],
                      "metodo": "error-claude", "tipo": parser.EXTENSIONES[ext]}
        except Exception as e:
            log.exception("No se pudo leer %s", nombre)
            salida = {"clientes": [], "errores": [{"entrada": nombre, "error": f"no se pudo leer: {e}"}],
                      "avisos": [], "metodo": "error", "tipo": parser.EXTENSIONES[ext]}
        finally:
            # Se guarda cifrado (puede contener NIF de personas físicas); el nombre es la huella del contenido
            destino = config.DIR_DOCUMENTOS / f"{huella}{ext}.enc"
            if not destino.exists():
                destino.write_bytes(user.cifrar_bytes(datos))
            tmp.unlink(missing_ok=True)
        did = db.registrar_documento(None, nombre, salida.get("tipo") or "otro", destino.name, huella, len(datos),
                                     salida.get("metodo"), g.usuario["id"])
        docs.append({"id": did, "nombre": nombre, "metodo": salida.get("metodo"),
                     "clientes": len(salida.get("clientes", []))})
        salidas.append(salida)
        db.auditar(g.usuario["id"], g.usuario["email"], "subida_documento", f"documento:{did}",
                   {"nombre": nombre, "sha256": huella, "metodo": salida.get("metodo"),
                    "clientes": len(salida.get("clientes", []))}, g.ip)
    res = parser.unir(*salidas)
    res["avisos"] += avisos_claude
    res["documentos"] = docs
    return jsonify(res)


@bp.route("/api/analizar-manual", methods=["POST"])
@requiere("consultar")
def analizar_manual():
    texto = (request.get_json(silent=True) or {}).get("texto", "")
    return jsonify(parser.procesar_manual(texto))


def _validar_periodo(datos) -> tuple[str, str, list[int]]:
    modo = datos.get("modo") if datos.get("modo") in ("movil", "ejercicios") else "movil"
    try:
        fecha_ref = date.fromisoformat(datos.get("fecha_referencia") or date.today().isoformat())
    except ValueError:
        abort(400, "Fecha de referencia no válida.")
    anos = []
    if modo == "ejercicios":
        try:
            anos = sorted({int(a) for a in datos.get("anos", [])})
        except (TypeError, ValueError):
            abort(400, "Años no válidos.")
        anos = anos or _anos_por_defecto()
        if len(anos) > 3 or any(a < 2010 or a > date.today().year + 1 for a in anos):
            abort(400, "Elija como máximo tres años entre 2010 y el próximo ejercicio.")
        if anos[-1] - anos[0] != len(anos) - 1:
            abort(400, "Los ejercicios deben ser consecutivos.")
    return modo, fecha_ref.isoformat(), anos


@bp.route("/api/consultas", methods=["POST"])
@requiere("consultar")
def crear():
    datos = request.get_json(silent=True) or {}
    modo, fecha_ref, anos = _validar_periodo(datos)
    clientes, errores = [], list(datos.get("errores", []))[:200]
    vistos = set()
    for c in datos.get("clientes", [])[:500]:
        cif, _, ok, motivo = parser.validar_identificador(str(c.get("cif", "")))
        if not ok:
            errores.append({"entrada": str(c.get("cif", ""))[:40], "error": motivo})
            continue
        if cif in vistos:
            continue
        vistos.add(cif)
        clientes.append({"cif": cif, "razon_social": (str(c.get("razon_social") or "").strip()[:160] or None),
                         "anos_solicitados": anos, "origen": str(c.get("origen") or "manual")[:200],
                         "confianza": _numero(c.get("confianza"), 1.0), "notas": str(c.get("notas") or "")[:500]})
    if not clientes:
        return jsonify({"error": "No hay ningún cliente con identificador válido."}), 400
    cid = str(uuid.uuid4())
    entrada = {"clientes": clientes, "errores": errores, "avisos": list(datos.get("avisos", []))[:100]}
    db.crear_consulta(cid, g.usuario["id"], modo, fecha_ref, anos, entrada)
    ids_docs = [int(i) for i in datos.get("documentos", []) if str(i).isdigit()]
    if ids_docs:
        db.asignar_documentos(ids_docs, cid)
    db.auditar(g.usuario["id"], g.usuario["email"], "consulta", f"consulta:{cid}",
               {"modo": modo, "fecha_referencia": fecha_ref, "anos": anos, "clientes": [c["cif"] for c in clientes],
                "documentos": ids_docs}, g.ip)
    session["ultima_consulta"] = cid
    orquestador.lanzar(cid)
    return jsonify({"id": cid, "url": url_for("resultados.ver", cid=cid)})


@bp.route("/api/progreso/<cid>")
@requiere("ver")
def progreso(cid):
    desde = request.args.get("desde", 0, type=int)
    p, log_, est = db.leer_progreso(cid, desde)
    if not p or not est:
        abort(404)
    return jsonify({"fase": p["fase"], "porcentaje": p["porcentaje"], "mensaje": p["mensaje"],
                    "estado": est["estado"], "error": est["mensaje_error"],
                    "log": [{"id": x["id"], "nivel": x["nivel"], "mensaje": x["mensaje"],
                             "hora": x["fecha_creacion"]} for x in log_]})


@bp.route("/api/consultas/<cid>/cancelar", methods=["POST"])
@requiere("consultar")
def cancelar(cid):
    q = db.consulta(cid) or abort(404)
    if q["estado"] == "en_proceso":
        db.pedir_cancelacion(cid)
        db.auditar(g.usuario["id"], g.usuario["email"], "cancelacion", f"consulta:{cid}", None, g.ip)
    return jsonify({"ok": True})


@bp.route("/consultas/<cid>/reintentar", methods=["POST"])
@requiere("consultar")
def reintentar(cid):
    q = db.consulta(cid) or abort(404)
    entrada = json.loads(q["clientes_buscados"])
    db.borrar_cache_cifs(c["cif"] for c in entrada["clientes"])  # «datos actuales»: nada de la caché
    nuevo = str(uuid.uuid4())
    db.crear_consulta(nuevo, g.usuario["id"], q["modo_periodo"],
                      date.today().isoformat() if q["modo_periodo"] == "movil" and request.form.get("hoy")
                      else q["fecha_referencia"], json.loads(q["anos_solicitados"]), entrada)
    db.auditar(g.usuario["id"], g.usuario["email"], "consulta", f"consulta:{nuevo}",
               {"reintento_de": cid, "clientes": [c["cif"] for c in entrada["clientes"]]}, g.ip)
    session["ultima_consulta"] = nuevo
    orquestador.lanzar(nuevo)
    flash("Consulta relanzada.", "ok")
    return redirect(url_for("resultados.ver", cid=nuevo))
