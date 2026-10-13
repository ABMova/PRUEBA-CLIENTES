"""Resultados de una consulta, ayudas declaradas por el cliente y exportación."""
import io
import re
import json
import zipfile
from datetime import date
from pathlib import Path

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, session, url_for

import config
from auth import user
from auth.permissions import puede, requiere
from logic.consultor import clase_reglamento
from models import db
from routes import orquestador

bp = Blueprint("resultados", __name__)

FORMATOS = {"docx": "Word", "pdf": "PDF", "xlsx": "Excel", "json": "JSON"}
REGLAMENTOS_MANUALES = {
    "REG (UE) 2023/2831 de minimis, General": "General (2023/2831)",
    "REG (UE) 1407/2013 de minimis": "General anterior (1407/2013)",
    "REG (UE) 1408/2013 de minimis": "Agrícola (1408/2013, mod. 2024/3118)",
    "REG (UE) 717/2014 de minimis": "Pesca (717/2014, mod. 2023/2391)",
    "REG (UE) 2023/2832 de minimis, SIEG": "SIEG (2023/2832)",
}


def _importe(texto: str) -> float:
    """Admite 1.234,56 · 1234,56 · 150.000 · 1234.56. Lo que sea ambiguo se rechaza."""
    t = texto.strip().replace(" ", "").replace("€", "")
    if "," in t:
        if not re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{1,2}|\d+,\d{1,2}", t):
            raise ValueError
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):  # puntos de miles: 150.000
        t = t.replace(".", "")
    elif not re.fullmatch(r"\d+(\.\d{1,2})?", t):
        raise ValueError
    valor = float(t)
    if valor <= 0:
        raise ValueError
    return round(valor, 2)


@bp.route("/consultas/<cid>")
@requiere("ver")
def ver(cid):
    q = db.consulta(cid) or abort(404)
    session["ultima_consulta"] = cid
    informe = json.loads(q["informe_json"])["informe"] if q.get("informe_json") else None
    if informe and puede("exportar"):
        from integrations import word_pdf
        word_pdf.calentar()  # la primera exportación de Word es lenta: que pase mientras se lee el resultado
    return render_template("resultados.html", q=q, informe=informe, entrada=json.loads(q["clientes_buscados"]),
                           documentos=db.documentos_de(cid), informes=db.informes_de(cid), formatos=FORMATOS,
                           reglamentos=REGLAMENTOS_MANUALES, hoy=date.today().isoformat())


@bp.route("/consultas/<cid>/exportar/<formato>")
@requiere("exportar")
def exportar(cid, formato):
    if formato not in FORMATOS:
        abort(404)
    q = db.consulta(cid) or abort(404)
    if q["estado"] != "completada":
        abort(400, "La consulta no ha terminado.")
    try:
        ruta = orquestador.exportar(cid, formato, g.usuario)
    except RuntimeError as e:  # sin Word ni LibreOffice para el PDF
        flash(str(e), "err")
        return redirect(url_for("resultados.ver", cid=cid) + "#exportar")
    db.auditar(g.usuario["id"], g.usuario["email"], "exportacion", f"consulta:{cid}",
               {"formato": formato, "fichero": ruta.name}, g.ip)
    return send_file(ruta, as_attachment=True, download_name=ruta.name)


@bp.route("/consultas/<cid>/exportar-todo")
@requiere("exportar")
def exportar_todo(cid):
    q = db.consulta(cid) or abort(404)
    if q["estado"] != "completada":
        abort(400, "La consulta no ha terminado.")
    try:
        rutas = orquestador.exportar_todo(cid, g.usuario)
    except RuntimeError as e:  # sin Word ni LibreOffice para el PDF
        flash(str(e), "err")
        return redirect(url_for("resultados.ver", cid=cid) + "#exportar")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rutas:
            z.write(r, r.name)
    buf.seek(0)
    nombre = rutas[0].stem + ".zip"
    db.auditar(g.usuario["id"], g.usuario["email"], "exportacion", f"consulta:{cid}",
               {"formato": "zip", "ficheros": [r.name for r in rutas]}, g.ip)
    return send_file(buf, as_attachment=True, download_name=nombre, mimetype="application/zip")


@bp.route("/informes/<int:iid>")
@requiere("ver")
def descargar_informe(iid):
    for inf in db.informes_de(request.args.get("consulta", "")):
        if inf["id"] == iid:
            ruta = Path(inf["ruta_fichero"])
            if ruta.exists():
                return send_file(ruta, as_attachment=True, download_name=ruta.name)
    abort(404)


@bp.route("/documentos/<int:did>")
@requiere("ver")
def descargar_documento(did):
    cid = request.args.get("consulta", "")
    for d in db.documentos_de(cid):
        if d["id"] == did:
            ruta = config.DIR_DOCUMENTOS / d["ruta_almacenada"]
            if not ruta.exists():
                abort(404)
            db.auditar(g.usuario["id"], g.usuario["email"], "descarga_documento", f"documento:{did}",
                       {"nombre": d["nombre_original"]}, g.ip)
            return send_file(io.BytesIO(user.descifrar_bytes(ruta.read_bytes())), as_attachment=True,
                             download_name=d["nombre_original"])
    abort(404)


@bp.route("/resultados/<int:rid>/ayudas", methods=["POST"])
@requiere("editar_resultados")
def anadir_ayuda(rid):
    r = db.resultado(rid) or abort(404)
    f = request.form
    try:
        fecha = date.fromisoformat(f.get("fecha_concesion", ""))
        importe = _importe(f.get("importe", ""))
    except ValueError:
        flash("Indique una fecha de concesión y un importe válidos.", "err")
        return redirect(url_for("resultados.ver", cid=r["consulta_id"]) + f"#cli-{rid}")
    reglamento = f.get("reglamento") if f.get("reglamento") in REGLAMENTOS_MANUALES else \
        "REG (UE) 2023/2831 de minimis, General"
    nueva = {
        "origen": "manual", "codigo_concesion": None, "fecha_concesion": fecha.isoformat(), "ano_fiscal": fecha.year,
        "programa": f.get("programa", "").strip()[:300] or "[PENDIENTE: programa]",
        "numero_convocatoria": None, "convocante": f.get("convocante", "").strip()[:300] or None,
        "reglamento": reglamento, "clase_reglamento": clase_reglamento(reglamento), "instrumento": None,
        "importe_concedido": importe, "fuente": "Declarada por el cliente", "url_referencia": None,
        "fecha_publicacion": None, "usuario_id": g.usuario["id"],
        "notas": f"Añadida por {g.usuario['nombre']} el {date.today():%d/%m/%Y}. " + f.get("notas", "").strip()[:300],
    }
    r["ayudas"].append(nueva)  # se guarda junto a las demás y se recalcula con todas
    db.actualizar_resultado(rid, r["detalles"], r["ayudas"])
    orquestador.recalcular_resultado(rid)
    db.auditar(g.usuario["id"], g.usuario["email"], "modificacion", f"resultado:{rid}",
               {"accion": "anadir_ayuda_declarada", "cif": r["cif"], "fecha": fecha.isoformat(), "importe": importe,
                "reglamento": reglamento}, g.ip)
    flash("Ayuda declarada añadida y saldo recalculado.", "ok")
    return redirect(url_for("resultados.ver", cid=r["consulta_id"]) + f"#cli-{rid}")


@bp.route("/resultados/<int:rid>/ayudas/<int:aid>/borrar", methods=["POST"])
@requiere("editar_resultados")
def borrar_ayuda(rid, aid):
    r = db.resultado(rid) or abort(404)
    quitada = next((a for a in r["ayudas"] if a["id"] == aid and a["origen"] == "manual"), None)
    if not quitada:
        abort(400, "Solo se pueden quitar las ayudas declaradas a mano.")
    r["ayudas"] = [a for a in r["ayudas"] if a["id"] != aid]
    db.actualizar_resultado(rid, r["detalles"], r["ayudas"])
    orquestador.recalcular_resultado(rid)
    db.auditar(g.usuario["id"], g.usuario["email"], "modificacion", f"resultado:{rid}",
               {"accion": "quitar_ayuda_declarada", "cif": r["cif"], "fecha": quitada["fecha_concesion"],
                "importe": quitada["importe_concedido"]}, g.ip)
    flash("Ayuda declarada quitada y saldo recalculado.", "ok")
    return redirect(url_for("resultados.ver", cid=r["consulta_id"]) + f"#cli-{rid}")
