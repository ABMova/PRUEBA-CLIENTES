"""Agente 3a · Generador de informe.

Consolida los cálculos en un informe estructurado. Solo hechos y cifras, sin
recomendaciones; lo que falta se marca [PENDIENTE: ...]. Es determinista a
propósito: un informe de saldos no debe cambiar de redacción entre dos
ejecuciones con los mismos datos.
"""
from datetime import date, datetime, timezone

from config import AVISO_BDNS
from logic.calculador import euros

ORDEN_ESTADO = {"SALDO_DISPONIBLE": 0, "LIMITE_ALCANZADO": 1, "LIMITE_SUPERADO": 2, "PENDIENTE": 3}
ETIQUETA_ESTADO = {
    "SALDO_DISPONIBLE": "Saldo disponible",
    "LIMITE_ALCANZADO": "En el límite",
    "LIMITE_SUPERADO": "Límite superado",
    "PENDIENTE": "Pendiente de revisión",
}
ETIQUETA_CLASE = {"general": "General", "agricola": "Agrícola", "pesca": "Pesca", "sieg": "SIEG",
                  "otro": "No identificado"}


def _fmt_fecha(iso: str | None) -> str | None:
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else None


def generar(consulta: dict, periodo: dict, resultados: list[dict], usuario: str,
            errores_entrada: list | None = None, avisos_entrada: list | None = None) -> dict:
    """`resultados` = filas guardadas (cálculo en `detalles` y ayudas en `ayudas`)."""
    detalle = []
    for r in resultados:
        d = r["detalles"]
        refs = [{
            "ayuda_id": a.get("id"),
            "programa": a.get("programa") or (f"Convocatoria BDNS {a['numero_convocatoria']}"
                                              if a.get("numero_convocatoria") else "[PENDIENTE: programa]"),
            "numero_convocatoria": a.get("numero_convocatoria"),
            "codigo_concesion": a.get("codigo_concesion"),
            "convocante": a.get("convocante"),
            "reglamento": a.get("reglamento"),
            "clase": ETIQUETA_CLASE.get(a.get("clase_reglamento") or "otro", "No identificado"),
            "instrumento": a.get("instrumento"),
            "ano": a.get("ano_fiscal"),
            "fecha_concesion": _fmt_fecha(a.get("fecha_concesion")),
            "importe": a.get("importe_concedido"),
            "computa": bool(a.get("computa")),
            "origen": a.get("origen"),
            "fuente": a.get("fuente") if a.get("origen") == "bdns" else "Declarada por el cliente",
            "url": a.get("url_referencia"),
            "notas": a.get("notas"),
        } for a in r["ayudas"]]
        detalle.append({
            "resultado_id": r["id"],
            "razon_social": d.get("razon_social_bdns") or d.get("razon_social") or "[PENDIENTE: razón social]",
            "razon_social_entrada": d.get("razon_social"),
            "cif": d["cif"],
            "saldo_disponible": d.get("saldo_disponible"),
            "estado": d["estado"],
            "estado_texto": ETIQUETA_ESTADO[d["estado"]],
            "anos_consultados": [x["ano"] for x in d.get("desglose_por_ano", [])],
            "desglose_por_ano": d.get("desglose_por_ano", []),
            "total_concedido": d.get("total_concedido_3anos"),
            "sumas_por_reglamento": d.get("sumas_por_reglamento", {}),
            "sublimites": d.get("sublimites", []),
            "liberaciones": d.get("liberaciones", []),
            "proxima_actualizacion_limite": _fmt_fecha(d.get("proxima_actualizacion_limite")),
            "fecha_recupera_saldo": _fmt_fecha(d.get("fecha_recupera_saldo")),
            "pendientes": d.get("pendientes", []),
            "notas": d.get("notas", ""),
            "notas_busqueda": d.get("notas_busqueda", ""),
            "confianza_busqueda": d.get("confianza_busqueda"),
            "url_beneficiario": d.get("url_beneficiario"),
            "referencias_fuente": refs,
        })
    detalle.sort(key=lambda x: (ORDEN_ESTADO[x["estado"]], -(x["saldo_disponible"] or 0)))

    con_saldo = [x for x in detalle if x["estado"] == "SALDO_DISPONIBLE"]
    en_limite = [x for x in detalle if x["estado"] == "LIMITE_ALCANZADO"]
    superado = [x for x in detalle if x["estado"] == "LIMITE_SUPERADO"]
    pendientes = [x for x in detalle if x["estado"] == "PENDIENTE" or x["pendientes"]]

    notas = [
        "Datos extraídos de fuentes públicas: " + AVISO_BDNS + " Requiere validación oficial.",
        f"Cálculo conforme al {periodo['reglamento']}: techo de {euros(periodo['techo'])} por única "
        f"empresa en el periodo {periodo['etiqueta']}.",
        "[PENDIENTE: única empresa] El techo se aplica al grupo de empresas vinculadas (art. 2.2 del "
        "Reglamento 2023/2831). La consulta solo cubre el CIF indicado: deben sumarse las ayudas de las "
        "empresas del mismo grupo.",
        "La BDNS registra las concesiones con retraso (las ventajas fiscales pueden tardar meses). Conviene "
        "completar el cálculo con la declaración responsable de ayudas de minimis del cliente.",
    ]
    notas += periodo.get("avisos", [])
    if pendientes:
        notas.append(f"{len(pendientes)} cliente(s) con datos marcados [PENDIENTE: ...] que requieren "
                     "confirmación manual.")

    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"informe": {
        "titulo": "Informe de Saldo Disponible de Ayudas de Minimis",
        "fecha_generacion": ahora,
        "usuario": usuario,
        "periodo_consulta": periodo["etiqueta"],
        "modo_periodo": periodo["modo"],
        "reglamento": periodo["reglamento"],
        "umbral": periodo["techo"],
        "resumen_ejecutivo": {
            "clientes_consultados": len(detalle),
            "clientes_con_saldo": len(con_saldo),
            "clientes_en_limite": len(en_limite),
            "clientes_superado_limite": len(superado),
            "clientes_pendientes": len(pendientes),
            "total_saldo_disponible_conjunto": round(sum(max(0, x["saldo_disponible"] or 0) for x in detalle), 2),
            "total_limite_superado": round(sum(-x["saldo_disponible"] for x in superado), 2),
            "total_concedido_periodo": round(sum(x["total_concedido"] or 0 for x in detalle), 2),
        },
        "detalle_clientes": detalle,
        "errores_entrada": errores_entrada or [],
        "avisos_entrada": avisos_entrada or [],
        "notas_importantes": notas,
        "audit_trail": {
            "consulta_id": consulta["id"],
            "usuario": usuario,
            "timestamp": consulta.get("fecha_consulta") or ahora,
            "parametros": {"modo": periodo["modo"], "anos": periodo["anos"],
                           "desde": periodo["desde"], "hasta": periodo["hasta"], "clientes": len(detalle)},
        },
    }}
