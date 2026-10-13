"""Agente 2b · Calculador de saldo de minimis. Lógica pura, sin IA.

Normativa aplicada (vigente a octubre de 2026):
- Reglamento (UE) 2023/2831 (general, desde el 01/01/2024): 300.000 € por
  única empresa en CUALQUIER periodo de tres años (periodo móvil que se cuenta
  hacia atrás desde la fecha de concesión de la nueva ayuda). Sustituye al
  Reglamento 1407/2013 (200.000 € en tres ejercicios fiscales), cuyas ayudas
  siguen contando dentro del periodo.
- Acumulación (art. 5 del 2023/2831): las de minimis agrícolas (1408/2013) y de
  pesca (717/2014) suman contra el mismo techo general; las SIEG (2023/2832)
  se acumulan con las generales hasta 750.000 €.
- Sublímites propios: agrícola 50.000 € (Reg. 2024/3118), pesca 40.000 €
  (Reg. 2023/2391), sobre el mismo periodo de tres años.

Dos modos:
- 'movil' (recomendado): tres años hasta la fecha de referencia.
- 'ejercicios': años naturales elegidos (criterio del antiguo 1407/2013), útil
  para revisar periodos pasados; con años >= 2024 es orientativo.
"""
from datetime import date

TECHO_GENERAL = 300_000.0
TECHO_GENERAL_1407 = 200_000.0
TECHO_SIEG_COMBINADO = 750_000.0
SUBLIMITE = {"agricola": 50_000.0, "pesca": 40_000.0}
MARGEN_LIMITE = 5_000.0
INICIO_2023_2831 = date(2024, 1, 1)


def sumar_anos(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year + n, day=28)


def _fecha(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def euros(x: float | None) -> str:
    if x is None:
        return "[PENDIENTE]"
    s = f"{abs(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if x < 0 else "") + s + " €"


def periodo(modo: str, fecha_ref: date, anos: list[int] | None) -> dict:
    """Ventana de cálculo, techo y avisos del periodo."""
    avisos = []
    if modo == "ejercicios":
        anos = sorted(set(anos or []))
        if not anos:
            anos = [fecha_ref.year - 3, fecha_ref.year - 2, fecha_ref.year - 1]
        desde, hasta = date(anos[0], 1, 1), date(anos[-1], 12, 31)
        if len(anos) != 3 or anos[-1] - anos[0] != 2:
            avisos.append("Periodo incompleto: la normativa exige tres ejercicios consecutivos; "
                          "añada los años que faltan para un cálculo conforme.")
        techo = TECHO_GENERAL if anos[-1] >= 2024 else TECHO_GENERAL_1407
        if anos[-1] >= 2024:
            avisos.append("Desde 2024 el Reglamento 2023/2831 computa tres años móviles, no ejercicios: "
                          "este cálculo por ejercicios es orientativo.")
        etiqueta = f"{anos[0]}-{anos[-1]}" if len(anos) > 1 else str(anos[0])
        return {"modo": modo, "desde": desde, "hasta": hasta, "techo": techo, "anos": anos,
                "etiqueta": etiqueta, "avisos": avisos,
                "reglamento": "Reglamento (UE) 2023/2831" if techo == TECHO_GENERAL else "Reglamento (UE) 1407/2013"}
    # móvil: (fecha_ref - 3 años, fecha_ref]
    desde = sumar_anos(fecha_ref, -3)
    techo = TECHO_GENERAL if fecha_ref >= INICIO_2023_2831 else TECHO_GENERAL_1407
    if techo == TECHO_GENERAL_1407:
        avisos.append("Fecha de referencia anterior a 2024: se aplica el techo de 200.000 € del Reglamento "
                      "1407/2013, que se medía por ejercicios fiscales; el periodo móvil es una aproximación.")
    anos = list(range(desde.year, fecha_ref.year + 1))
    return {"modo": "movil", "desde": desde, "hasta": fecha_ref, "techo": techo, "anos": anos,
            "etiqueta": f"{desde.strftime('%d/%m/%Y')} – {fecha_ref.strftime('%d/%m/%Y')}", "avisos": avisos,
            "reglamento": "Reglamento (UE) 2023/2831" if techo == TECHO_GENERAL else "Reglamento (UE) 1407/2013"}


def _en_periodo(f: date, per: dict) -> bool:
    if per["modo"] == "movil":
        return per["desde"] < f <= per["hasta"]
    return per["desde"] <= f <= per["hasta"]


def _saldo(sumas: dict, techo: float) -> float:
    computa_general = sumas["general"] + sumas["otro"] + sumas["agricola"] + sumas["pesca"]
    saldo = techo - computa_general
    if sumas["sieg"]:
        saldo = min(saldo, TECHO_SIEG_COMBINADO - computa_general - sumas["sieg"])
    return round(saldo, 2)


def _estado(saldo: float) -> str:
    if saldo < 0:
        return "LIMITE_SUPERADO"
    if saldo <= MARGEN_LIMITE:
        return "LIMITE_ALCANZADO"
    return "SALDO_DISPONIBLE"


def calcular_cliente(res: dict, per: dict) -> tuple[dict, list[dict]]:
    """-> (cálculo, ayudas marcadas con `computa`). `res` es un resultado del Consultor
    (o el mismo con ayudas manuales añadidas)."""
    techo = per["techo"]
    pendientes, notas = [], []
    ayudas = [dict(a) for a in res.get("ayudas_minimis_encontradas", [])]

    base = {
        "cif": res["cif"], "razon_social": res.get("razon_social"),
        "razon_social_bdns": res.get("razon_social_bdns"), "umbral_minimo": techo,
        "reglamento_aplicado": per["reglamento"], "periodo_referencia": per["etiqueta"],
        "modo_periodo": per["modo"], "fecha_desde": per["desde"].isoformat(),
        "fecha_hasta": per["hasta"].isoformat(), "confianza_busqueda": res.get("confianza_busqueda"),
        "url_beneficiario": res.get("url_beneficiario"), "notas_busqueda": res.get("notas_busqueda") or "",
    }

    if not res.get("busqueda_completa", True):
        pendientes.append("[PENDIENTE: búsqueda en la BDNS incompleta, requiere revisión manual]")
        base.update({"desglose_por_ano": [], "total_concedido_3anos": None, "saldo_disponible": None,
                     "estado": "PENDIENTE", "pendientes": pendientes, "liberaciones": [],
                     "proxima_actualizacion_limite": None, "fecha_recupera_saldo": None,
                     "sumas_por_reglamento": {}, "sublimites": [],
                     "notas": res.get("notas_busqueda") or "Búsqueda incompleta."})
        return base, ayudas

    sumas = {"general": 0.0, "agricola": 0.0, "pesca": 0.0, "sieg": 0.0, "otro": 0.0}
    por_ano: dict[int, float] = {a: 0.0 for a in per["anos"]}
    computables = []
    for a in ayudas:
        f = _fecha(a.get("fecha_concesion"))
        a["computa"] = False
        if f is None:
            pendientes.append(f"[PENDIENTE: fecha de concesión de {a.get('codigo_concesion') or 'una ayuda'}]")
            continue
        if f > per["hasta"]:
            a["notas"] = "Posterior a la fecha de referencia: no computa."
            continue
        if not _en_periodo(f, per):
            continue
        a["computa"] = True
        clase = a.get("clase_reglamento") or "otro"
        sumas[clase] = sumas.get(clase, 0.0) + float(a.get("importe_concedido") or 0)
        por_ano[f.year] = por_ano.get(f.year, 0.0) + float(a.get("importe_concedido") or 0)
        computables.append((f, float(a.get("importe_concedido") or 0), clase))

    if sumas["otro"]:
        notas.append(f"{euros(sumas['otro'])} con reglamento no identificado se suman al techo general por prudencia.")

    total = round(sum(sumas.values()), 2)
    saldo = _saldo(sumas, techo)
    estado = _estado(saldo)

    sublimites = []
    if techo == TECHO_GENERAL:
        for clase, tope in SUBLIMITE.items():
            if sumas[clase]:
                sublimites.append({"clase": clase, "tope": tope, "computado": round(sumas[clase], 2),
                                   "disponible": round(min(tope - sumas[clase], saldo), 2)})
    if sumas["sieg"]:
        notas.append("Incluye ayudas SIEG (Reg. 2023/2832): se aplica también el techo combinado de 750.000 €.")

    # Calendario de liberaciones: cuándo sale cada ayuda del periodo
    liberaciones = []
    if per["modo"] == "movil":
        restante = dict(sumas)
        for f, imp, clase in sorted(computables):
            sale = sumar_anos(f, 3)
            restante[clase] -= imp
            liberaciones.append({"fecha": sale.isoformat(), "importe": round(imp, 2),
                                 "saldo_tras_liberar": _saldo(restante, techo)})
        # Agrupar las del mismo día
        agrupadas: dict[str, dict] = {}
        for l in liberaciones:
            g = agrupadas.setdefault(l["fecha"], {"fecha": l["fecha"], "importe": 0.0, "saldo_tras_liberar": 0})
            g["importe"] = round(g["importe"] + l["importe"], 2)
            g["saldo_tras_liberar"] = l["saldo_tras_liberar"]
        liberaciones = list(agrupadas.values())
    else:
        anos = per["anos"]
        acumulado = dict(sumas)
        for ano in anos:
            imp_ano = por_ano.get(ano, 0.0)
            # se aproxima liberando por año completo, sin distinguir reglamento
            acumulado["general"] -= imp_ano
            liberaciones.append({"fecha": date(ano + 3, 1, 1).isoformat(), "importe": round(imp_ano, 2),
                                 "saldo_tras_liberar": _saldo(acumulado, techo)})

    proxima = next((l["fecha"] for l in liberaciones if l["importe"] > 0), None)
    recupera = None
    if estado != "SALDO_DISPONIBLE":
        recupera = next((l["fecha"] for l in liberaciones if l["saldo_tras_liberar"] > MARGEN_LIMITE), None)
        if estado == "LIMITE_SUPERADO":
            notas.append(f"Ha superado el techo de {euros(techo)} en el periodo {per['etiqueta']}. "
                         "No puede recibir nuevas ayudas de minimis"
                         + (f" hasta el {date.fromisoformat(recupera).strftime('%d/%m/%Y')}, fecha en que "
                            "sale del periodo la ayuda más antigua necesaria" if recupera else "")
                         + ", salvo nuevas concesiones registradas después de esta consulta.")
        else:
            notas.append(f"Saldo igual o inferior a {euros(MARGEN_LIMITE)}: prácticamente en el límite.")
    else:
        notas.append("Empresa dentro del techo de minimis en el periodo consultado.")

    if res.get("confianza_busqueda") == "no encontrado":
        pendientes.append("[PENDIENTE: el CIF no figura en la BDNS; confirmar con declaración responsable "
                          "del cliente]")
    if res.get("confianza_busqueda") == "media":
        pendientes.append("[PENDIENTE: confirmar identidad del beneficiario, ver notas de búsqueda]")
    pendientes += [f"[PENDIENTE: {a}]" for a in per["avisos"] if a.startswith("Periodo incompleto")]

    base.update({
        "desglose_por_ano": [{"ano": a, "importe_concedido": round(v, 2), "base_imponible": True}
                             for a, v in sorted(por_ano.items())],
        "sumas_por_reglamento": {k: round(v, 2) for k, v in sumas.items() if v},
        "total_concedido_3anos": total,
        "saldo_disponible": saldo,
        "estado": estado,
        "sublimites": sublimites,
        "liberaciones": liberaciones,
        "proxima_actualizacion_limite": proxima,
        "fecha_recupera_saldo": recupera,
        "pendientes": pendientes,
        "notas": " ".join(notas),
        "n_ayudas_periodo": len(computables),
        "n_ayudas_total": len(ayudas),
    })
    return base, ayudas


def calcular(resultados_consultor: dict, modo: str, fecha_ref: date, anos: list[int] | None) -> dict:
    per = periodo(modo, fecha_ref, anos)
    calculos = []
    for res in resultados_consultor.get("resultados", []):
        calc, ayudas = calcular_cliente(res, per)
        calc["_ayudas"] = ayudas
        calculos.append(calc)
    return {"periodo": {**per, "desde": per["desde"].isoformat(), "hasta": per["hasta"].isoformat()},
            "calculos_saldo": calculos}
