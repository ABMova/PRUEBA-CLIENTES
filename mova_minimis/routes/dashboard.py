"""Página principal: cifras, últimas consultas y buscador del historial."""
from flask import Blueprint, render_template, request

from auth.permissions import requiere
from models import db

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@requiere("ver")
def inicio():
    texto = request.args.get("q", "").strip()
    consultas = db.listar_consultas(limite=100 if texto else 15, texto=texto or None)
    return render_template("dashboard.html", consultas=consultas, texto=texto,
                           estados=db.contar_consultas_por_estado())
