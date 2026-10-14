"""Orquestación de la cadena de agentes y persistencia de cada fase.

Los agentes (logic/) no saben de SQL ni de HTTP: aquí se les inyecta la red,
la caché, el progreso y la cancelación, y se guarda lo que devuelven.
"""
import json
import logging
import threading
from datetime import date

import config
from auth import user
from integrations import claude_api, web_scraper
from logic import calculador, consultor, exportador, generador
from models import db

log = logging.getLogger(__name__)


class Cancelada(Exception):
    pass


# ---------------------------------------------------------------- Claude
def clave_claude() -> str | None:
    cifrada = db.leer_ajuste("anthropic_api_key")
    if cifrada:
        clave = user.descifrar(cifrada)
        if clave:
            return clave
    import os
    return os.environ.get("ANTHROPIC_API_KEY") or None


def modelo_claude() -> str:
    m = db.leer_ajuste("modelo_parser", config.MODELO_POR_DEFECTO)
    return m if m in config.MODELOS_CLAUDE else config.MODELO_POR_DEFECTO


def llamador_claude(aviso=None):
    """Función para el Parser, o None si no hay clave configurada."""
    clave = clave_claude()
    if not clave:
        return None
    modelo = modelo_claude()

    def llamar(sistema, bloques, esquema):
        datos, uso = claude_api.llamar_json(clave, modelo, sistema, bloques, esquema, max_tokens=4000, aviso=aviso)
        log.info("Claude %s: %s tokens de entrada, %s de salida", uso["modelo"], uso["entrada"], uso["salida"])
        return datos
    return llamar


# ---------------------------------------------------------------- informe
def periodo_de(consulta: dict) -> dict:
    per = calculador.periodo(consulta["modo_periodo"], date.fromisoformat(consulta["fecha_referencia"]),
                             json.loads(consulta["anos_solicitados"]))
    return {**per, "desde": per["desde"].isoformat(), "hasta": per["hasta"].isoformat()}


def regenerar_informe(cid: str) -> dict:
    q = db.consulta(cid)
    entrada = json.loads(q["clientes_buscados"])
    inf = generador.generar(q, periodo_de(q), db.resultados_de(cid), q["usuario_nombre"],
                            entrada.get("errores"), entrada.get("avisos"))
    db.actualizar_consulta(cid, informe_json=json.dumps(inf, ensure_ascii=False))
    return inf


def informe_al_dia(cid: str) -> dict | None:
    """El informe guardado; si es de antes de la 1.1.4 (sin saldo a 1 de enero), se recalcula con sus mismas
    ayudas: no vuelve a consultar la BDNS."""
    q = db.consulta(cid)
    if not q.get("informe_json"):
        return None
    inf = json.loads(q["informe_json"])
    if "etiqueta_saldo_enero" not in inf["informe"]:
        for r in db.resultados_de(cid):
            recalcular_resultado(r["id"], regenerar=False)
        inf = regenerar_informe(cid)
    return inf


def _informe_para_exportar(cid: str) -> dict:
    q = db.consulta(cid)
    inf = informe_al_dia(cid) or regenerar_informe(cid)
    inf["informe"]["usuario"] = q["usuario_nombre"]
    return inf


def exportar(cid: str, formato: str, usuario: dict):
    inf = _informe_para_exportar(cid)
    base = exportador.nombre_base(inf["informe"])
    if formato == "json":
        ruta = config.DIR_INFORMES / f"{base}.json"
        ruta.write_text(json.dumps(inf, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        ruta = exportador.exportar(inf, formato, config.DIR_INFORMES, base)
    db.registrar_informe(cid, formato, str(ruta), usuario["id"])
    return ruta


def exportar_todo(cid: str, usuario: dict) -> list:
    """Word, PDF y Excel. Word y PDF de una sola pasada: el PDF sale del mismo .docx."""
    inf = _informe_para_exportar(cid)
    base = exportador.nombre_base(inf["informe"])
    rutas = exportador.exportar_mova(inf, config.DIR_INFORMES, base, {"docx", "pdf"})
    rutas["xlsx"] = exportador.exportar(inf, "xlsx", config.DIR_INFORMES, base)
    for formato, ruta in rutas.items():
        db.registrar_informe(cid, formato, str(ruta), usuario["id"])
    return [rutas["docx"], rutas["pdf"], rutas["xlsx"]]


# ---------------------------------------------------------------- recalcular un resultado
def recalcular_resultado(rid: int, regenerar: bool = True) -> None:
    r = db.resultado(rid)
    q = db.consulta(r["consulta_id"])
    d = r["detalles"]
    per = calculador.periodo(q["modo_periodo"], date.fromisoformat(q["fecha_referencia"]),
                             json.loads(q["anos_solicitados"]))
    res = {
        "cif": d["cif"], "razon_social": d.get("razon_social"), "razon_social_bdns": d.get("razon_social_bdns"),
        "confianza_busqueda": d.get("confianza_busqueda"), "busqueda_completa": d["estado"] != "PENDIENTE",
        "notas_busqueda": d.get("notas_busqueda"), "url_beneficiario": d.get("url_beneficiario"),
        "ayudas_minimis_encontradas": r["ayudas"],
    }
    calc, ayudas = calculador.calcular_cliente(res, per)
    db.actualizar_resultado(rid, calc, ayudas)
    if regenerar:
        regenerar_informe(r["consulta_id"])


# ---------------------------------------------------------------- la cadena en un hilo
def lanzar(cid: str) -> None:
    h = threading.Thread(target=_ejecutar, args=(cid,), name=f"consulta-{cid[:8]}", daemon=True)
    h.start()


def _ejecutar(cid: str) -> None:
    def cancelado():
        return db.cancelacion_pedida(cid)

    try:
        q = db.consulta(cid)
        entrada = json.loads(q["clientes_buscados"])
        clientes = entrada["clientes"]
        n = len(clientes)
        db.progreso(cid, "Consulta BDNS", 5, f"{n} cliente(s) a consultar en la Base de Datos Nacional de Subvenciones")

        def prog(i, total, msg):
            if cancelado():
                raise Cancelada()
            db.progreso(cid, "Consulta BDNS", 5 + int(65 * i / max(total, 1)), msg)

        salida = consultor.consultar(clientes, web_scraper, cache_get=db.leer_cache, cache_set=db.guardar_cache,
                                     progreso=prog, cancelado=cancelado)
        if cancelado():
            raise Cancelada()
        for r in salida["resultados"]:
            nivel = "aviso" if r["confianza_busqueda"] != "alta" else "info"
            db.registrar(cid, f"{r['cif']}: {len(r['ayudas_minimis_encontradas'])} concesión(es) de minimis "
                              f"en la BDNS · confianza {r['confianza_busqueda']}"
                              + (f" · {r['notas_busqueda']}" if r["notas_busqueda"] else ""), nivel)

        db.progreso(cid, "Cálculo de saldo", 75, "Aplicando el techo de minimis al periodo de referencia")
        calc = calculador.calcular(salida, q["modo_periodo"], date.fromisoformat(q["fecha_referencia"]),
                                   json.loads(q["anos_solicitados"]))
        db.borrar_resultados(cid)
        for c in calc["calculos_saldo"]:
            ayudas = c.pop("_ayudas")
            db.guardar_resultado(cid, c, ayudas)
            db.registrar(cid, f"{c['cif']}: {c['estado']} · saldo {calculador.euros(c['saldo_disponible'])}")
        for aviso in calc["periodo"]["avisos"]:
            db.registrar(cid, aviso, "aviso")

        if cancelado():
            raise Cancelada()
        db.progreso(cid, "Informe", 90, "Consolidando el informe")
        regenerar_informe(cid)
        db.actualizar_consulta(cid, estado="completada")
        db.progreso(cid, "Completada", 100, "Consulta terminada")
        db.auditar(q["usuario_id"], q["usuario_email"], "consulta_completada", f"consulta:{cid}",
                   {"clientes": n, "modo": q["modo_periodo"]})
    except Cancelada:
        db.actualizar_consulta(cid, estado="cancelada", mensaje_error="Cancelada por el usuario")
        db.progreso(cid, "Cancelada", 100, "Consulta cancelada por el usuario")
    except Exception as e:
        log.exception("Fallo en la consulta %s", cid)
        db.actualizar_consulta(cid, estado="error", mensaje_error=str(e)[:500])
        db.progreso(cid, "Error", 100, f"Error: {e}")
