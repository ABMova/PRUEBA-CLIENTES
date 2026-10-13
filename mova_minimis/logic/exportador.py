"""Agente 3b · Exportador a Word, PDF y Excel.

Word y PDF salen con el formato corporativo de la skill «mova-informes»: el informe se escribe en su
Markdown y lo maqueta su motor (logic/informe_mova.py) sobre plantillas_informe/plantilla_mova.docx;
el PDF sale del propio .docx (Word, o LibreOffice si no hay Word). El Excel es propio (openpyxl).
Determinista: no necesita IA y el documento es idéntico cada vez. Sin macros ni contraseñas.
"""
import re
from datetime import datetime
from pathlib import Path

from logic.calculador import euros

DORADO = "B8892F"       # --gold-d: legible sobre blanco (el #d9b45b se pierde en papel)
DORADO_CLARO = "D9B45B"
OSCURO = "141518"       # --card
LEYENDA = "Datos extraídos de fuentes públicas. Requiere validación oficial."


def _fecha_local(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def nombre_base(informe: dict) -> str:
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"informe_minimis_{marca}_{informe['audit_trail']['consulta_id'][:8]}"


# Word, PDF y Excel solo enseñan las ayudas que computan en el periodo, sin la lista de referencias de fuente
_SIN_AYUDAS = "Sin ayudas de minimis que computen en el periodo."


def _computan(d: dict) -> list[dict]:
    return [x for x in d["referencias_fuente"] if x["computa"]]


def _kpis(inf: dict) -> list[tuple[str, str]]:
    r = inf["resumen_ejecutivo"]
    return [
        ("Clientes consultados", str(r["clientes_consultados"])),
        ("Con saldo disponible", str(r["clientes_con_saldo"])),
        ("En el límite (≤ 5.000 €)", str(r["clientes_en_limite"])),
        ("Límite superado", str(r["clientes_superado_limite"])),
        ("Con datos pendientes", str(r["clientes_pendientes"])),
        ("Saldo disponible conjunto", euros(r["total_saldo_disponible_conjunto"])),
        ("Total concedido en el periodo", euros(r["total_concedido_periodo"])),
        ("Exceso sobre el techo", euros(r["total_limite_superado"])),
    ]


# ======================================================================= WORD Y PDF (formato MOVA)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _fecha_larga(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return iso
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _md(texto) -> str:
    """Texto de datos dentro del Markdown: sin saltos ni caracteres que el motor lea como marcas."""
    t = " ".join(str("" if texto is None else texto).split())
    return t.replace("|", "/").replace("*", "·")


def _tabla(cabecera: list[str], filas: list[list]) -> list[str]:
    lineas = ["| " + " | ".join(cabecera) + " |", "|" + "---|" * len(cabecera)]
    lineas += ["| " + " | ".join(_md(c) for c in f) + " |" for f in filas]
    return lineas + [""]


def _reglamento_corto(x: dict) -> str:
    """'REG (UE) 2023/2831 de minimis, General' -> 'General · 2023/2831'."""
    numero = re.search(r"\d{3,4}/\d{4}", x.get("reglamento") or "")
    return f"{x['clase']} · {numero.group(0)}" if numero else (x.get("clase") or "")


def markdown_informe(informe: dict) -> str:
    """El informe en la sintaxis de la skill mova-informes (references/formato_entrada.md)."""
    inf = informe["informe"]
    r = inf["resumen_ejecutivo"]
    m = [
        "---",
        "tipo: Informe",
        f"titulo: {_md(inf['titulo'])}",
        f"subtitulo: {_md(inf['reglamento'])} · techo de {euros(inf['umbral'])} por única empresa",
        f"clientes consultados: {r['clientes_consultados']}",
        f"periodo de calculo: {_md(inf['periodo_consulta'])}",
        f"fecha: {_fecha_larga(inf['fecha_generacion'])}",
        f"consulta: {inf['audit_trail']['consulta_id']}",
        f"elaborado por: {_md(inf['usuario'])}",
        "confidencial: si",
        "autor: MOVA",
        "---",
        "",
        "# Resumen ejecutivo",
        "",
        f"Se ha consultado la Base de Datos Nacional de Subvenciones (BDNS) para {r['clientes_consultados']} "
        f"cliente(s) y se ha calculado el saldo disponible de ayudas de minimis conforme al {_md(inf['reglamento'])}, "
        f"en el periodo {_md(inf['periodo_consulta'])}.",
        "",
    ]
    m += _tabla(["Indicador", "Valor"], _kpis(inf))
    m += [f"> **Resultado:** {r['clientes_con_saldo']} cliente(s) con saldo disponible; "
          f"{r['clientes_en_limite'] + r['clientes_superado_limite']} en el límite o por encima del techo. "
          f"Saldo disponible conjunto: {euros(r['total_saldo_disponible_conjunto'])}.", ""]

    m += ["# Detalle por cliente", ""]
    m += _tabla(["Cliente", "CIF", "Saldo disponible", "Estado", "Computado"],
                [[d["razon_social"], d["cif"], euros(d["saldo_disponible"]), d["estado_texto"],
                  euros(d["total_concedido"])] for d in inf["detalle_clientes"]])
    for d in inf["detalle_clientes"]:
        m += [f"## {_md(d['razon_social'])}", "",
              f"**CIF:** {d['cif']}. **Estado:** {_md(d['estado_texto'])}. **Saldo disponible:** "
              f"{euros(d['saldo_disponible'])}. **Computado en el periodo:** {euros(d['total_concedido'])}.", ""]
        if d["desglose_por_ano"]:
            m += _tabla(["Año", "Importe computado"],
                        [[f"{x['ano']}" + (f" ({x['tramo']})" if x.get("tramo") else ""), euros(x["importe_concedido"])]
                         for x in d["desglose_por_ano"]])
        hechos = []
        if d["proxima_actualizacion_limite"]:
            hechos.append(f"Próxima salida de una ayuda del periodo: {d['proxima_actualizacion_limite']}.")
        if d["fecha_recupera_saldo"]:
            hechos.append(f"Vuelve a tener saldo a partir del {d['fecha_recupera_saldo']}.")
        for s in d["sublimites"]:
            hechos.append(f"Sublímite {s['clase']} ({_md(s.get('norma', ''))}): computado {euros(s['computado'])} "
                          f"de {euros(s['tope'])}; disponible {euros(s['disponible'])}.")
        m += [f"- {_md(h)}" for h in hechos] + ([""] if hechos else [])
        computan = _computan(d)
        if computan:
            m += [f"### Ayudas que computan en el periodo", ""]
            # Cuatro columnas: el motor reparte el ancho por longitud de texto, y con el concedente en su propia
            # columna la fecha y el importe quedaban tan estrechos que se partían
            m += _tabla(["Fecha", "Convocatoria / programa · concedente", "Reglamento", "Importe"],
                        [[x["fecha_concesion"], f"{x['programa']} · {x['convocante']}" if x["convocante"] else x["programa"],
                          _reglamento_corto(x), euros(x["importe"])] for x in computan]
                        + [["TOTAL", "", "", euros(sum(x["importe"] or 0 for x in computan))]])
        else:
            m += [_SIN_AYUDAS, ""]
        for p in d["pendientes"]:  # el motor resalta [PENDIENTE: ...] en amarillo y negrita
            m += [_md(p), ""]
        if d["notas"]:
            m += [_md(d["notas"]), ""]
        if d["notas_busqueda"]:
            m += [f"*Búsqueda: {_md(d['notas_busqueda'])}*", ""]

    if inf.get("errores_entrada"):
        m += ["# Entradas descartadas", "",
              "Identificadores leídos de los documentos o de la entrada manual que no se han consultado.", ""]
        m += _tabla(["Entrada", "Motivo"], [[e["entrada"], e["error"]] for e in inf["errores_entrada"]])

    m += ["# Notas importantes", ""] + [f"- {_md(n)}" for n in inf["notas_importantes"]] + [""]
    return "\n".join(m)


def exportar_mova(informe: dict, carpeta: Path, base: str, formatos: set[str]) -> dict[str, Path]:
    """Word y/o PDF con la plantilla MOVA. El PDF sale del propio .docx (como pide la skill)."""
    import tempfile
    from integrations import word_pdf
    from logic import informe_mova

    carpeta.mkdir(parents=True, exist_ok=True)
    docx, pdf = carpeta / f"{base}.docx", carpeta / f"{base}.pdf"
    with tempfile.TemporaryDirectory(prefix="mova_md_") as tmp:
        md = Path(tmp) / "informe.md"
        md.write_text(markdown_informe(informe), encoding="utf-8")
        meta, bloques = informe_mova.lee_entrada(md)
        gen = informe_mova.GeneradorInforme(meta, bloques, md.parent).construye()
        gen.guarda(docx, None)
        # Word: actualiza el índice con las páginas reales, guarda y exporta el PDF en el mismo paso
        if not word_pdf.preparar(docx, pdf if "pdf" in formatos else None):
            if "pdf" in formatos:  # sin Word: LibreOffice, con la medición de páginas de la skill
                with_indice = gen._marca_indice is not None
                paginas = None
                if with_indice:
                    prov = Path(tmp) / "provisional.docx"
                    gen.guarda(prov, {t["marcador"]: 88 for t in gen.titulos})
                    try:
                        paginas = informe_mova.paginas_de_titulos(
                            informe_mova.docx_a_pdf(prov, Path(tmp)), [t for t in gen.titulos if t["nivel"] <= 2])
                    except RuntimeError as e:
                        raise RuntimeError("Para el PDF hace falta Word o LibreOffice en este equipo.") from e
                    gen = informe_mova.GeneradorInforme(meta, bloques, md.parent).construye()
                    gen.guarda(docx, paginas)
                generado = informe_mova.docx_a_pdf(docx, carpeta)
                if generado != pdf:
                    generado.replace(pdf)
            # solo Word sin Word instalado: el .docx pide actualizar el índice al abrirlo
    salida = {}
    if "docx" in formatos:
        salida["docx"] = docx
    else:
        docx.unlink(missing_ok=True)
    if "pdf" in formatos:
        salida["pdf"] = pdf
    return salida


# ======================================================================= EXCEL
def exportar_xlsx(informe: dict, destino: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    inf = informe["informe"]
    wb = Workbook()
    moneda = '#,##0.00 "€";[Red]-#,##0.00 "€"'
    cab_fill = PatternFill("solid", fgColor=OSCURO)
    cab_font = Font(bold=True, color=DORADO_CLARO)
    fino = Side(style="thin", color="C9C9C9")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)

    def cabecera(ws, fila, textos, anchos):
        for i, (t, w) in enumerate(zip(textos, anchos), start=1):
            c = ws.cell(row=fila, column=i, value=t)
            c.fill, c.font, c.border = cab_fill, cab_font, borde
            c.alignment = Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = ws.cell(row=fila + 1, column=1)

    # Hoja 1 · Resumen
    ws = wb.active
    ws.title = "Resumen"
    ws["A1"] = inf["titulo"]
    ws["A1"].font = Font(bold=True, size=14, color=DORADO)
    meta = [("Periodo de consulta", inf["periodo_consulta"]), ("Normativa", inf["reglamento"]),
            ("Techo aplicado", inf["umbral"]), ("Consultado por", inf["usuario"]),
            ("Fecha de generación", _fecha_local(inf["fecha_generacion"])),
            ("Consulta", inf["audit_trail"]["consulta_id"]), ("Aviso", LEYENDA)]
    for i, (k, v) in enumerate(meta, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = ws.cell(row=i, column=2, value=v)
        if k == "Techo aplicado":
            c.number_format = moneda
    fila0 = len(meta) + 4
    cabecera(ws, fila0, ["Indicador", "Valor"], [34, 44])
    r = inf["resumen_ejecutivo"]
    indicadores = [("Clientes consultados", r["clientes_consultados"], None),
                   ("Con saldo disponible", r["clientes_con_saldo"], None),
                   ("En el límite (≤ 5.000 €)", r["clientes_en_limite"], None),
                   ("Límite superado", r["clientes_superado_limite"], None),
                   ("Con datos pendientes", r["clientes_pendientes"], None),
                   ("Saldo disponible conjunto", r["total_saldo_disponible_conjunto"], moneda),
                   ("Total concedido en el periodo", r["total_concedido_periodo"], moneda),
                   ("Exceso sobre el techo", r["total_limite_superado"], moneda)]
    for i, (k, v, fmt) in enumerate(indicadores, start=fila0 + 1):
        ws.cell(row=i, column=1, value=k).border = borde
        c = ws.cell(row=i, column=2, value=v)
        c.border = borde
        c.alignment = Alignment(horizontal="right")
        if fmt:
            c.number_format = fmt
    ws.freeze_panes = None

    # Hoja 2 · Detalle
    wd = wb.create_sheet("Detalle")
    cabecera(wd, 1, ["CIF", "Razón social", "Saldo disponible", "Estado", "Años consultados", "Total concedido",
                     "Próxima salida del periodo", "Recupera saldo", "Pendientes", "Notas"],
             [12, 40, 16, 20, 18, 16, 16, 14, 50, 70])
    for i, d in enumerate(inf["detalle_clientes"], start=2):
        valores = [d["cif"], d["razon_social"], d["saldo_disponible"], d["estado_texto"],
                   ", ".join(map(str, d["anos_consultados"])), d["total_concedido"],
                   d["proxima_actualizacion_limite"], d["fecha_recupera_saldo"],
                   " ".join(d["pendientes"]), d["notas"]]
        for j, v in enumerate(valores, start=1):
            c = wd.cell(row=i, column=j, value=v)
            c.border = borde
            c.alignment = Alignment(vertical="top", wrap_text=j in (2, 9, 10))
            if j in (3, 6):
                c.number_format = moneda
    n = len(inf["detalle_clientes"])
    if n:
        tot = n + 2
        wd.cell(row=tot, column=2, value="TOTAL").font = Font(bold=True)
        for col in (3, 6):
            letra = get_column_letter(col)
            # el saldo negativo (límite superado) no resta del saldo conjunto, igual que en el resumen
            formula = f'=SUMIF({letra}2:{letra}{n + 1},">0")' if col == 3 else f"=SUM({letra}2:{letra}{n + 1})"
            c = wd.cell(row=tot, column=col, value=formula)
            c.number_format, c.font = moneda, Font(bold=True)
        rango = f"A2:J{n + 1}"
        for texto, color in (("Saldo disponible", "DCFCE7"), ("En el límite", "FEF3C7"),
                             ("Límite superado", "FEE2E2"), ("Pendiente de revisión", "E5E7EB")):
            wd.conditional_formatting.add(rango, FormulaRule(formula=[f'$D2="{texto}"'],
                                                             fill=PatternFill("solid", fgColor=color)))
    wd.auto_filter.ref = f"A1:J{max(n, 1) + 1}"

    # Hoja 3 · Ayudas computadas (como en Word y PDF: sin referencias de fuente ni ayudas que no computan)
    wr = wb.create_sheet("Ayudas computadas")
    cabecera(wr, 1, ["CIF", "Razón social", "Programa / convocatoria", "Nº convocatoria BDNS", "Código concesión",
                     "Concedente", "Reglamento", "Instrumento", "Año", "Fecha concesión", "Importe"],
             [12, 32, 50, 14, 16, 40, 30, 18, 7, 13, 15])
    fila = 2
    for d in inf["detalle_clientes"]:
        for x in _computan(d):
            valores = [d["cif"], d["razon_social"], x["programa"], x["numero_convocatoria"], x["codigo_concesion"],
                       x["convocante"], x["reglamento"], x["instrumento"], x["ano"], x["fecha_concesion"], x["importe"]]
            for j, v in enumerate(valores, start=1):
                c = wr.cell(row=fila, column=j, value=v)
                c.border = borde
                if j == 11:
                    c.number_format = moneda
            fila += 1
    wr.auto_filter.ref = f"A1:K{max(fila - 1, 1)}"

    wb.properties.creator = "MOVA IA · MOVA Minimis"
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def exportar(informe: dict, formato: str, carpeta: Path, base: str | None = None) -> Path:
    base = base or nombre_base(informe["informe"])
    if formato == "xlsx":
        return exportar_xlsx(informe, carpeta / f"{base}.xlsx")
    return exportar_mova(informe, carpeta, base, {formato})[formato]
