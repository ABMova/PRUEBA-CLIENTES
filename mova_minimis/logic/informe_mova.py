#!/usr/bin/env python3
"""
COPIA EN MOVA MINIMIS del motor de la skill «mova-informes» (scripts/generar_informe.py).
Cambios respecto al original, para que funcione dentro de la aplicación:
  - La plantilla se lee de plantillas_informe/plantilla_mova.docx (config.RAIZ_CODIGO, dentro del .exe).
  - Las páginas del índice se miden con pypdf: en los equipos no hay pdftotext.
  - LibreOffice se busca también en su ruta de instalación habitual de Windows.
La conversión con Word la hace integrations/word_pdf.py (actualiza el índice y exporta el PDF).
Si la skill cambia, volver a copiar el script y repetir estos cambios.

Genera informes con la identidad visual MOVA en Word (.docx) y PDF.

Parte SIEMPRE de assets/plantilla_mova.docx (logo, marca de agua del edificio
y pie con datos de contacto) y vuelca el contenido escrito en Markdown.
El PDF se obtiene convirtiendo el mismo .docx, para que ambos formatos
sean visualmente identicos.

Uso:
    python generar_informe.py entrada.md --salida /ruta/Informe --formato ambos
    python generar_informe.py entrada.md --salida Informe --formato docx
    python generar_informe.py entrada.md --salida Informe --formato pdf

Sintaxis de entrada: ver references/formato_entrada.md
"""
from __future__ import annotations

import argparse
import copy
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips

log = logging.getLogger("mova-informes")

import config  # noqa: E402

PLANTILLA = config.RAIZ_CODIGO / "plantillas_informe" / "plantilla_mova.docx"

# ---------------------------------------------------------------------------
# Identidad visual (derivada de la plantilla oficial)
# ---------------------------------------------------------------------------
FUENTE = "Microsoft YaHei UI"          # tipografia corporativa de la plantilla
FUENTE_PDF_SUSTITUTA = "Noto Sans CJK SC"  # solo si YaHei no esta instalada al generar el PDF
NEGRO = "1A1A1A"
TEXTO = "262626"
GRIS = "595959"
GRIS_MEDIO = "8C8C8C"
GRIS_LINEA = "BFBFBF"
FONDO = "F2F2F2"
ANCHO_UTIL = 9638  # dxa: A4 (11906) - margenes izq/der de la plantilla (1134 + 1134)

CLAVES_RESERVADAS = {"tipo", "titulo", "título", "subtitulo", "subtítulo", "portada", "indice",
                     "índice", "numerar", "autor", "confidencial", "paginacion", "paginación"}


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------
def mayus_sin_tildes(texto: str) -> str:
    """Mayusculas sin tildes (norma de estilo del usuario). Conserva la Ñ y la Ü."""
    salida = []
    for ch in texto.upper():
        if ch in "ÑÜ":
            salida.append(ch)
            continue
        base = unicodedata.normalize("NFD", ch)
        salida.append("".join(c for c in base if unicodedata.category(c) != "Mn"))
    return unicodedata.normalize("NFC", "".join(salida))


def normaliza_busqueda(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", "", t).upper()


def es_sino(valor: str | None, defecto: bool) -> bool:
    if valor is None:
        return defecto
    return valor.strip().lower() in {"si", "sí", "s", "yes", "true", "1"}


# ---------------------------------------------------------------------------
# Utilidades XML
# ---------------------------------------------------------------------------
def fija_fuente(rpr_owner, tam: float | None = None, negrita=None, cursiva=None, color: str | None = None):
    """Aplica fuente corporativa a un estilo o run (python-docx)."""
    f = rpr_owner.font
    f.name = FUENTE
    rpr = rpr_owner.element.get_or_add_rPr() if hasattr(rpr_owner.element, "get_or_add_rPr") else rpr_owner.element.rPr
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for atr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(atr), FUENTE)
    if tam is not None:
        f.size = Pt(tam)
    if negrita is not None:
        f.bold = negrita
    if cursiva is not None:
        f.italic = cursiva
    if color:
        f.color.rgb = RGBColor.from_string(color)


def borde_parrafo(parrafo_o_estilo, lado="bottom", sz=6, color=NEGRO, espacio=4):
    el = parrafo_o_estilo._p if hasattr(parrafo_o_estilo, "_p") else parrafo_o_estilo.element
    ppr = el.get_or_add_pPr()
    pbdr = ppr.find(qn("w:pBdr"))
    if pbdr is None:
        pbdr = OxmlElement("w:pBdr")
        ppr.append(pbdr)
    b = OxmlElement(f"w:{lado}")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), str(sz))
    b.set(qn("w:space"), str(espacio))
    b.set(qn("w:color"), color)
    pbdr.append(b)


def nivel_esquema(estilo, nivel: int):
    ppr = estilo.element.get_or_add_pPr()
    ol = OxmlElement("w:outlineLvl")
    ol.set(qn("w:val"), str(nivel))
    ppr.append(ol)


def sombrea_celda(celda, color: str):
    tcpr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcpr.append(shd)


def bordes_celda(celda, **lados):
    """lados: top=(sz,color) | None para quitar."""
    tcpr = celda._tc.get_or_add_tcPr()
    tcb = tcpr.find(qn("w:tcBorders"))
    if tcb is None:
        tcb = OxmlElement("w:tcBorders")
        tcpr.append(tcb)
    for lado in ("top", "left", "bottom", "right"):
        if lado not in lados:
            continue
        el = OxmlElement(f"w:{lado}")
        if lados[lado] is None:
            el.set(qn("w:val"), "nil")
        else:
            sz, color = lados[lado]
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color)
        tcb.append(el)


def ancho_celda(celda, dxa: int):
    tcpr = celda._tc.get_or_add_tcPr()
    tcw = tcpr.find(qn("w:tcW"))
    if tcw is None:
        tcw = OxmlElement("w:tcW")
        tcpr.insert(0, tcw)
    tcw.set(qn("w:w"), str(dxa))
    tcw.set(qn("w:type"), "dxa")


def configura_tabla(tabla, anchos: list[int], bordes: dict, margen=(60, 100)):
    tbl = tabla._tbl
    tblpr = tbl.tblPr
    for tag in ("w:tblW", "w:tblLayout", "w:tblBorders", "w:tblCellMar", "w:tblStyle"):
        for el in tblpr.findall(qn(tag)):
            tblpr.remove(el)
    tblw = OxmlElement("w:tblW")
    tblw.set(qn("w:w"), str(sum(anchos)))
    tblw.set(qn("w:type"), "dxa")
    tblpr.append(tblw)
    tblb = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{lado}")
        if bordes.get(lado):
            sz, color = bordes[lado]
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color)
        else:
            el.set(qn("w:val"), "nil")
        tblb.append(el)
    tblpr.append(tblb)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblpr.append(lay)
    mar = OxmlElement("w:tblCellMar")
    for lado, val in (("top", margen[0]), ("left", margen[1]), ("bottom", margen[0]), ("right", margen[1])):
        el = OxmlElement(f"w:{lado}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)
    grid = tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(anchos[i]))
    for fila in tabla.rows:
        for i, celda in enumerate(fila.cells):
            ancho_celda(celda, anchos[i])


def campo(parrafo, instruccion: str, texto_cache: str = "1", tam: float = 8, color: str | None = None):
    """Inserta un campo simple (PAGE, NUMPAGES...) con resultado en cache."""
    def run_con(el):
        r = parrafo.add_run()
        fija_fuente(r, tam, color=color)
        r._r.append(el)
        return r
    b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin"); run_con(b)
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instruccion} "; run_con(it)
    s = OxmlElement("w:fldChar"); s.set(qn("w:fldCharType"), "separate"); run_con(s)
    r = parrafo.add_run(texto_cache); fija_fuente(r, tam, color=color)
    e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end"); run_con(e)


# Orden de hijos exigido por el esquema OOXML (Word rechaza el fichero si no se respeta)
ORDEN_ESQUEMA = {
    "pPr": "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs "
           "suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd "
           "snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment "
           "textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange",
    "rPr": "ins del moveFrom moveTo rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint "
           "noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText "
           "vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange",
    "tcPr": "cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark",
    "tblPr": "tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing tblInd "
             "tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription",
    "trPr": "cnfStyle divId gridBefore gridAfter wBefore wAfter cantSplit trHeight tblHeader tblCellSpacing jc hidden",
    "pBdr": "top left bottom right between bar",
    "tcBorders": "top start left bottom end right insideH insideV tl2br tr2bl",
    "tblBorders": "top start left bottom end right insideH insideV",
}
ORDEN_ESQUEMA = {k: {n: i for i, n in enumerate(v.split())} for k, v in ORDEN_ESQUEMA.items()}
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def ordena_esquema(raiz):
    for el in raiz.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(W_NS):
            continue
        orden = ORDEN_ESQUEMA.get(el.tag[len(W_NS):])
        if not orden:
            continue
        hijos = list(el)
        clave = lambda h: orden.get(h.tag[len(W_NS):], 999) if isinstance(h.tag, str) and h.tag.startswith(W_NS) else 999
        nuevos = sorted(hijos, key=clave)  # sorted es estable
        if nuevos != hijos:
            for h in hijos:
                el.remove(h)
            el.extend(nuevos)


# ---------------------------------------------------------------------------
# Lectura del Markdown
# ---------------------------------------------------------------------------
def lee_entrada(ruta: Path) -> tuple[dict, list[dict]]:
    texto = ruta.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta: dict[str, str] = {}
    lineas = texto.split("\n")
    if lineas and lineas[0].strip() == "---":
        fin = next((i for i in range(1, len(lineas)) if lineas[i].strip() == "---"), None)
        if fin is None:
            raise ValueError("Cabecera de metadatos sin cerrar (falta la segunda linea '---').")
        for ln in lineas[1:fin]:
            if ":" in ln and ln.strip():
                k, v = ln.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        lineas = lineas[fin + 1:]
    return meta, parsea_bloques(lineas)


RE_LISTA = re.compile(r"^(\s*)([-*]|\d+[.)])\s+(.*)$")
RE_IMAGEN = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")
RE_FIRMA = re.compile(r"^\[\[FIRMA:(.*)\]\]\s*$", re.I)


def parsea_bloques(lineas: list[str]) -> list[dict]:
    bloques: list[dict] = []
    i = 0
    parrafo: list[str] = []

    def cierra_parrafo():
        if parrafo:
            bloques.append({"tipo": "p", "texto": " ".join(s.strip() for s in parrafo)})
            parrafo.clear()

    while i < len(lineas):
        ln = lineas[i]
        st = ln.strip()
        if not st:
            cierra_parrafo(); i += 1; continue
        m = re.match(r"^(#{1,3})\s+(.*)$", st)
        if m:
            cierra_parrafo()
            bloques.append({"tipo": f"h{len(m.group(1))}", "texto": m.group(2).strip()}); i += 1; continue
        if st.upper() == "[[SALTO]]":
            cierra_parrafo(); bloques.append({"tipo": "salto"}); i += 1; continue
        mf = RE_FIRMA.match(st)
        if mf:
            cierra_parrafo()
            partes = [p.strip() for p in mf.group(1).split("|")]
            bloques.append({"tipo": "firma", "lineas": partes}); i += 1; continue
        mi = RE_IMAGEN.match(st)
        if mi:
            cierra_parrafo(); bloques.append({"tipo": "imagen", "pie": mi.group(1), "ruta": mi.group(2)}); i += 1; continue
        if st.startswith("|"):
            cierra_parrafo()
            filas = []
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                fila = lineas[i].strip().strip("|")
                celdas = [c.strip() for c in fila.split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas if c):
                    filas.append(celdas)
                i += 1
            bloques.append({"tipo": "tabla", "filas": filas}); continue
        if st.startswith(">"):
            cierra_parrafo()
            txt = []
            while i < len(lineas) and lineas[i].strip().startswith(">"):
                txt.append(lineas[i].strip()[1:].strip()); i += 1
            bloques.append({"tipo": "destacado", "texto": " ".join(t for t in txt if t)}); continue
        ml = RE_LISTA.match(ln)
        if ml:
            cierra_parrafo()
            items = []
            ordenada = ml.group(2)[0].isdigit()
            while i < len(lineas):
                m2 = RE_LISTA.match(lineas[i])
                if not m2:
                    # continuacion de item con sangria
                    if lineas[i].startswith("  ") and lineas[i].strip() and items:
                        items[-1]["texto"] += " " + lineas[i].strip(); i += 1; continue
                    break
                nivel = min(len(m2.group(1).replace("\t", "  ")) // 2, 2)
                items.append({"nivel": nivel, "texto": m2.group(3).strip()})
                i += 1
            bloques.append({"tipo": "lista", "ordenada": ordenada, "items": items}); continue
        parrafo.append(ln); i += 1
    cierra_parrafo()
    return bloques


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------
RE_INLINE = re.compile(r"(\*\*.+?\*\*|\[PENDIENTE[^\]]*\]|\*[^*\s][^*]*?\*)")


class GeneradorInforme:
    def __init__(self, meta: dict, bloques: list[dict], carpeta_md: Path):
        if not PLANTILLA.exists():
            raise FileNotFoundError(f"No se encuentra la plantilla: {PLANTILLA}")
        self.meta = meta
        self.bloques = bloques
        self.carpeta_md = carpeta_md
        self.doc = Document(str(PLANTILLA))
        self.numerar = es_sino(meta.get("numerar"), True)
        self.salto_pendiente = False
        self.titulos: list[dict] = []   # para el indice
        self.n_fig = 0
        self.n_tab = 0
        self.bookmark_id = 100
        self._prepara_documento()

    # -- preparacion -------------------------------------------------------
    def _prepara_documento(self):
        body = self.doc.element.body
        for hijo in list(body):
            if hijo.tag != qn("w:sectPr"):
                body.remove(hijo)
        self._estilos()
        self._compacta_cabecera_pie()
        self._numeracion()
        self._pie_paginacion()
        props = self.doc.core_properties
        props.title = self.meta.get("titulo") or self.meta.get("título") or "Informe"
        props.author = self.meta.get("autor", "MOVA")
        props.comments = ""
        props.last_modified_by = self.meta.get("autor", "MOVA")

    def _estilo(self, nombre, base="Normal"):
        estilos = self.doc.styles
        try:
            return estilos[nombre]
        except KeyError:
            st = estilos.add_style(nombre, WD_STYLE_TYPE.PARAGRAPH, builtin=nombre.lower().startswith(("heading", "toc", "caption")))
            if base:
                st.base_style = estilos[base]
            return st

    def _estilos(self):
        normal = self.doc.styles["Normal"]
        fija_fuente(normal, 10, color=TEXTO)
        pf = normal.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(6)
        pf.line_spacing = 1.15
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf.widow_control = True

        h1 = self._estilo("Heading 1")
        fija_fuente(h1, 13, negrita=True, color=NEGRO)
        h1.paragraph_format.space_before = Pt(20)
        h1.paragraph_format.space_after = Pt(10)
        h1.paragraph_format.keep_with_next = True
        h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        h1.paragraph_format.line_spacing = 1.0
        borde_parrafo(h1, "bottom", sz=6, color=NEGRO, espacio=4)
        nivel_esquema(h1, 0)

        h2 = self._estilo("Heading 2")
        fija_fuente(h2, 11, negrita=True, color=NEGRO)
        h2.paragraph_format.space_before = Pt(14)
        h2.paragraph_format.space_after = Pt(5)
        h2.paragraph_format.keep_with_next = True
        h2.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        nivel_esquema(h2, 1)

        h3 = self._estilo("Heading 3")
        fija_fuente(h3, 10, negrita=True, color=GRIS)
        h3.paragraph_format.space_before = Pt(10)
        h3.paragraph_format.space_after = Pt(3)
        h3.paragraph_format.keep_with_next = True
        h3.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        nivel_esquema(h3, 2)

        for n, (tam, neg, sangria, antes) in {"toc 1": (10, True, 0, 6), "toc 2": (9.5, False, 0.6, 2), "toc 3": (9, False, 1.2, 0)}.items():
            t = self._estilo(n)
            fija_fuente(t, tam, negrita=neg, color=TEXTO if neg else GRIS)
            t.paragraph_format.space_before = Pt(antes)
            t.paragraph_format.space_after = Pt(2)
            t.paragraph_format.left_indent = Cm(sangria)
            t.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            t.paragraph_format.tab_stops.add_tab_stop(Twips(ANCHO_UTIL), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)

        cap = self._estilo("Caption")
        fija_fuente(cap, 8.5, negrita=False, cursiva=True, color=GRIS)
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_before = Pt(3)
        cap.paragraph_format.space_after = Pt(10)

        tt = self._estilo("MOVA Tabla")
        fija_fuente(tt, 9, color=TEXTO)
        tt.paragraph_format.space_after = Pt(0)
        tt.paragraph_format.line_spacing = 1.0
        tt.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

        li = self._estilo("MOVA Lista")
        li.paragraph_format.space_after = Pt(3)

    def _compacta_cabecera_pie(self):
        """Los parrafos de cabecera y pie conservan el interlineado original de la plantilla."""
        sec = self.doc.sections[0]
        for parte in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer,
                      sec.even_page_header, sec.even_page_footer):
            if parte.is_linked_to_previous:
                continue
            for p in parte.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    def _numeracion(self):
        num_part = self.doc.part.numbering_part
        el = num_part.element
        ids_abs = [int(a.get(qn("w:abstractNumId"))) for a in el.findall(qn("w:abstractNum"))]
        self.abs_viñeta = max(ids_abs + [0]) + 1
        self.abs_orden = self.abs_viñeta + 1

        def abstract(abs_id, niveles):
            a = OxmlElement("w:abstractNum")
            a.set(qn("w:abstractNumId"), str(abs_id))
            mlt = OxmlElement("w:multiLevelType"); mlt.set(qn("w:val"), "hybridMultilevel"); a.append(mlt)
            for ilvl, (fmt, texto, izq) in enumerate(niveles):
                lvl = OxmlElement("w:lvl"); lvl.set(qn("w:ilvl"), str(ilvl))
                for tag, val in (("w:start", "1"), ("w:numFmt", fmt), ("w:lvlText", texto), ("w:lvlJc", "left")):
                    x = OxmlElement(tag); x.set(qn("w:val"), val); lvl.append(x)
                ppr = OxmlElement("w:pPr"); ind = OxmlElement("w:ind")
                ind.set(qn("w:left"), str(izq)); ind.set(qn("w:hanging"), "284"); ppr.append(ind); lvl.append(ppr)
                rpr = OxmlElement("w:rPr"); rf = OxmlElement("w:rFonts")
                for atr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                    rf.set(qn(atr), FUENTE)
                rpr.append(rf)
                col = OxmlElement("w:color"); col.set(qn("w:val"), NEGRO); rpr.append(col)
                lvl.append(rpr)
                a.append(lvl)
            return a

        vin = abstract(self.abs_viñeta, [("bullet", "•", 567), ("bullet", "–", 1134), ("bullet", "·", 1701)])
        ordn = abstract(self.abs_orden, [("decimal", "%1.", 567), ("lowerLetter", "%2)", 1134), ("lowerRoman", "%3.", 1701)])
        primer_num = el.find(qn("w:num"))
        for a in (vin, ordn):
            if primer_num is not None:
                primer_num.addprevious(a)
            else:
                el.append(a)
        self._num_el = el
        self.num_viñeta = self._nuevo_num(self.abs_viñeta)

    def _nuevo_num(self, abs_id: int) -> int:
        ids = [int(n.get(qn("w:numId"))) for n in self._num_el.findall(qn("w:num"))]
        nid = max(ids + [0]) + 1
        n = OxmlElement("w:num"); n.set(qn("w:numId"), str(nid))
        an = OxmlElement("w:abstractNumId"); an.set(qn("w:val"), str(abs_id)); n.append(an)
        ov = OxmlElement("w:lvlOverride"); ov.set(qn("w:ilvl"), "0")
        so = OxmlElement("w:startOverride"); so.set(qn("w:val"), "1"); ov.append(so); n.append(ov)
        self._num_el.append(n)
        return nid

    def _pie_paginacion(self):
        if not es_sino(self.meta.get("paginacion") or self.meta.get("paginación"), True):
            return
        pie = self.doc.sections[0].footer
        destino = None
        for p in pie.paragraphs:
            if re.search(r"\d{3}\s?\d{3}\s?\d{3}", p.text):
                destino = p
                break
        if destino is None:
            destino = pie.paragraphs[-1]
        destino.paragraph_format.tab_stops.add_tab_stop(Twips(ANCHO_UTIL), WD_TAB_ALIGNMENT.RIGHT)
        r = destino.add_run("\t"); fija_fuente(r, 8)
        r = destino.add_run("Página "); fija_fuente(r, 8, color=GRIS)
        campo(destino, "PAGE", "1", 8, GRIS)
        r = destino.add_run(" de "); fija_fuente(r, 8, color=GRIS)
        campo(destino, "NUMPAGES", "1", 8, GRIS)

    # -- piezas basicas ----------------------------------------------------
    def _parrafo(self, estilo="Normal"):
        p = self.doc.add_paragraph(style=estilo)
        if self.salto_pendiente:
            p.paragraph_format.page_break_before = True
            self.salto_pendiente = False
        return p

    def _texto_enriquecido(self, parrafo, texto: str, tam: float | None = None, color: str | None = None, negrita_base=False):
        for trozo in RE_INLINE.split(texto):
            if not trozo:
                continue
            neg, cur, pend = negrita_base, False, False
            if trozo.startswith("**") and trozo.endswith("**") and len(trozo) > 4:
                trozo, neg = trozo[2:-2], True
            elif trozo.startswith("[PENDIENTE"):
                pend = True
            elif trozo.startswith("*") and trozo.endswith("*") and len(trozo) > 2:
                trozo, cur = trozo[1:-1], True
            r = parrafo.add_run(trozo)
            if tam or color or neg or cur:
                fija_fuente(r, tam, negrita=neg or None, cursiva=cur or None, color=color)
            if pend:
                fija_fuente(r, tam, negrita=True, color=NEGRO)
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        return parrafo

    def _espaciador(self, puntos=4):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing = Pt(puntos)
        r = p.add_run(""); r.font.size = Pt(2)
        return p

    # -- portada -----------------------------------------------------------
    def portada(self):
        m = self.meta
        titulo = m.get("titulo") or m.get("título") or "Informe"
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Cm(5.2)
        p.paragraph_format.space_after = Pt(10)
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(mayus_sin_tildes(m.get("tipo", "Informe")))
        fija_fuente(r, 9, negrita=True, color=GRIS)
        sp = OxmlElement("w:spacing"); sp.set(qn("w:val"), "40"); r._r.get_or_add_rPr().append(sp)

        p = self.doc.add_paragraph()
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(10)
        p.paragraph_format.right_indent = Cm(2)
        r = p.add_run(titulo); fija_fuente(r, 24, negrita=True, color=NEGRO)

        sub = m.get("subtitulo") or m.get("subtítulo")
        if sub:
            p = self.doc.add_paragraph()
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.right_indent = Cm(3)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(sub); fija_fuente(r, 12.5, color=GRIS)

        # filete corto
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.right_indent = Twips(ANCHO_UTIL - 1700)
        p.paragraph_format.line_spacing = Pt(6)
        borde_parrafo(p, "bottom", sz=18, color=NEGRO, espacio=1)

        datos = [(k, v) for k, v in m.items() if k not in CLAVES_RESERVADAS and v]
        if datos:
            sep = self.doc.add_paragraph(); sep.paragraph_format.space_before = Cm(5.5); sep.paragraph_format.space_after = Pt(0)
            sep.paragraph_format.line_spacing = Pt(2)
            anchos = [2600, ANCHO_UTIL - 2600]
            t = self.doc.add_table(rows=len(datos), cols=2)
            t.alignment = WD_TABLE_ALIGNMENT.LEFT
            configura_tabla(t, anchos, {"top": (8, NEGRO), "bottom": (4, GRIS_LINEA), "insideH": (4, GRIS_LINEA)}, margen=(70, 0))
            for fila, (k, v) in zip(t.rows, datos):
                c0, c1 = fila.cells
                for c in (c0, c1):
                    c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                p0 = c0.paragraphs[0]; p0.style = self.doc.styles["MOVA Tabla"]
                r = p0.add_run(mayus_sin_tildes(k)); fija_fuente(r, 7.5, negrita=True, color=GRIS_MEDIO)
                p1 = c1.paragraphs[0]; p1.style = self.doc.styles["MOVA Tabla"]
                self._texto_enriquecido(p1, v, tam=10, color=NEGRO)
        if es_sino(m.get("confidencial"), False):
            p = self.doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            r = p.add_run("Documento confidencial. Uso exclusivo del destinatario.")
            fija_fuente(r, 8, cursiva=True, color=GRIS_MEDIO)
        self.salto_pendiente = True

    # -- indice ------------------------------------------------------------
    def indice(self):
        p = self._parrafo()
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(12)
        borde_parrafo(p, "bottom", sz=6, color=NEGRO, espacio=4)
        r = p.add_run("INDICE"); fija_fuente(r, 13, negrita=True, color=NEGRO)
        self._marca_indice = self.doc.add_paragraph()  # ancla: se sustituye al final
        self.salto_pendiente = True

    def _rellena_indice(self, paginas: dict[str, int] | None):
        ancla = self._marca_indice._p
        entradas = [t for t in self.titulos if t["nivel"] <= 2]
        if not entradas:
            ancla.getparent().remove(ancla); return
        parrafos = []
        for idx, t in enumerate(entradas):
            p = self.doc.add_paragraph(style=f"toc {t['nivel']}")
            if idx == 0:
                for tipo, txt in (("begin", None), ("instr", 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None)):
                    r = p.add_run()
                    if tipo == "instr":
                        el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = f" {txt} "
                    else:
                        el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), tipo)
                    r._r.append(el)
            hl = OxmlElement("w:hyperlink"); hl.set(qn("w:anchor"), t["marcador"]); hl.set(qn("w:history"), "1")
            pag = str(paginas.get(t["marcador"], "")) if paginas else ""
            for texto in (t["texto_indice"], "\t", pag):
                r = OxmlElement("w:r")
                rpr = OxmlElement("w:rPr"); rf = OxmlElement("w:rFonts")
                for atr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                    rf.set(qn(atr), FUENTE)
                rpr.append(rf); r.append(rpr)
                if texto == "\t":
                    r.append(OxmlElement("w:tab"))
                else:
                    te = OxmlElement("w:t"); te.set(qn("xml:space"), "preserve"); te.text = texto; r.append(te)
                hl.append(r)
            p._p.append(hl)
            if idx == len(entradas) - 1:
                r = p.add_run(); el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), "end"); r._r.append(el)
            parrafos.append(p._p)
        for pp in parrafos:
            ancla.addprevious(pp)
        ancla.getparent().remove(ancla)

    # -- bloques de contenido ---------------------------------------------
    def titulo(self, nivel: int, texto: str):
        if self.numerar:
            if not hasattr(self, "_cont"):
                self._cont = [0, 0, 0]
            self._cont[nivel - 1] += 1
            for j in range(nivel, 3):
                self._cont[j] = 0
            prefijo = ".".join(str(c) for c in self._cont[:nivel]) + ("." if nivel == 1 else "")
            texto_final = f"{prefijo} {texto}"
        else:
            texto_final = texto
        if nivel == 1:
            texto_final = mayus_sin_tildes(texto_final)
        p = self._parrafo(f"Heading {nivel}")
        self.bookmark_id += 1
        marcador = f"_Toc{self.bookmark_id:08d}"
        bs = OxmlElement("w:bookmarkStart"); bs.set(qn("w:id"), str(self.bookmark_id)); bs.set(qn("w:name"), marcador)
        p._p.append(bs)
        p.add_run(texto_final)
        be = OxmlElement("w:bookmarkEnd"); be.set(qn("w:id"), str(self.bookmark_id))
        p._p.append(be)
        self.titulos.append({"nivel": nivel, "texto_indice": texto_final, "marcador": marcador})

    def parrafo(self, texto: str):
        self._texto_enriquecido(self._parrafo(), texto)

    def lista(self, ordenada: bool, items: list[dict]):
        num_id = self._nuevo_num(self.abs_orden) if ordenada else self.num_viñeta
        for it in items:
            p = self._parrafo("MOVA Lista")
            ppr = p._p.get_or_add_pPr()
            numpr = OxmlElement("w:numPr")
            il = OxmlElement("w:ilvl"); il.set(qn("w:val"), str(it["nivel"])); numpr.append(il)
            ni = OxmlElement("w:numId"); ni.set(qn("w:val"), str(num_id)); numpr.append(ni)
            ppr.append(numpr)
            self._texto_enriquecido(p, it["texto"])
        if items:
            p.paragraph_format.space_after = Pt(8)

    def tabla(self, filas: list[list[str]]):
        if not filas:
            return
        ncol = max(len(f) for f in filas)
        filas = [f + [""] * (ncol - len(f)) for f in filas]
        pesos = []
        for c in range(ncol):
            textos = [re.sub(r"\*\*|\*", "", f[c]) for f in filas]
            largo = max(len(x) for x in textos)
            palabra = max((len(w) for x in textos for w in x.split()), default=4)
            pesos.append(max(min(max(largo, 6), 45), palabra + 3))
        total = sum(pesos)
        anchos = [int(ANCHO_UTIL * w / total) for w in pesos]
        anchos[-1] += ANCHO_UTIL - sum(anchos)
        numerica = re.compile(r"^[-+]?[\d.\s]*\d(,\d+)?\s*(€|%|EUR|eur)?$")

        col_num = []
        for c in range(1, ncol):
            valores = [re.sub(r"\*", "", f[c]).strip() for f in filas[1:] if f[c].strip()]
            col_num.append(bool(valores) and sum(bool(numerica.match(v)) for v in valores) >= len(valores) / 2)
        col_num = [False] + col_num

        if self.salto_pendiente:
            self._espaciador().paragraph_format.page_break_before = True
            self.salto_pendiente = False
        t = self.doc.add_table(rows=len(filas), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        configura_tabla(t, anchos, {"top": (8, NEGRO), "bottom": (8, NEGRO), "insideH": (4, GRIS_LINEA)})
        for i, (fila_doc, datos) in enumerate(zip(t.rows, filas)):
            trpr = fila_doc._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit"); trpr.append(cs)
            es_cab = i == 0
            es_total = (not es_cab) and mayus_sin_tildes(re.sub(r"\*", "", datos[0])).startswith("TOTAL")
            if es_cab:
                th = OxmlElement("w:tblHeader"); trpr.append(th)
            for j, (celda, txt) in enumerate(zip(fila_doc.cells, datos)):
                celda.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                p = celda.paragraphs[0]
                p.style = self.doc.styles["MOVA Tabla"]
                limpio = re.sub(r"\*", "", txt).strip()
                if col_num[j] and (es_cab or not limpio or numerica.match(limpio)):
                    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if es_cab:
                    sombrea_celda(celda, NEGRO)
                    self._texto_enriquecido(p, limpio, tam=8.5, color="FFFFFF", negrita_base=True)
                elif es_total:
                    sombrea_celda(celda, FONDO)
                    bordes_celda(celda, top=(8, NEGRO))
                    self._texto_enriquecido(p, limpio, tam=9, color=NEGRO, negrita_base=True)
                else:
                    self._texto_enriquecido(p, txt, tam=9)
        self._espaciador(8)

    def destacado(self, texto: str):
        if self.salto_pendiente:
            self._espaciador().paragraph_format.page_break_before = True
            self.salto_pendiente = False
        t = self.doc.add_table(rows=1, cols=1)
        configura_tabla(t, [ANCHO_UTIL], {"left": (24, NEGRO)}, margen=(110, 200))
        c = t.rows[0].cells[0]
        sombrea_celda(c, FONDO)
        p = c.paragraphs[0]
        p.style = self.doc.styles["MOVA Tabla"]
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.15
        self._texto_enriquecido(p, texto, tam=9.5, color=TEXTO)
        self._espaciador(8)

    def imagen(self, ruta: str, pie: str):
        ruta_img = Path(ruta)
        if not ruta_img.is_absolute():
            ruta_img = self.carpeta_md / ruta_img
        if not ruta_img.exists():
            log.warning("Imagen no encontrada: %s. Se inserta marcador de pendiente.", ruta_img)
            self.parrafo(f"[PENDIENTE: imagen {ruta_img.name}]")
            return
        p = self._parrafo()
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_after = Pt(0)
        from PIL import Image
        with Image.open(ruta_img) as im:
            w, h = im.size
        ancho_max_cm, alto_max_cm = 16.0, 12.0
        ancho_cm = min(ancho_max_cm, alto_max_cm * w / h)
        p.add_run().add_picture(str(ruta_img), width=Cm(ancho_cm))
        if pie:
            self.n_fig += 1
            c = self.doc.add_paragraph(style="Caption")
            c.add_run(f"Figura {self.n_fig}. {pie}")

    def firma(self, lineas: list[str]):
        p = self._parrafo()
        p.paragraph_format.space_before = Pt(28)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for i, ln in enumerate(lineas):
            r = p.add_run(ln)
            fija_fuente(r, 10 if i == 0 else 9, negrita=(i == 0), color=NEGRO if i == 0 else GRIS)
            if i < len(lineas) - 1:
                r.add_break()

    # -- orquestacion ------------------------------------------------------
    def construye(self):
        if es_sino(self.meta.get("portada"), True):
            self.portada()
        if es_sino(self.meta.get("indice") or self.meta.get("índice"), True):
            self.indice()
        else:
            self._marca_indice = None
        for b in self.bloques:
            tipo = b["tipo"]
            if tipo in ("h1", "h2", "h3"):
                self.titulo(int(tipo[1]), b["texto"])
            elif tipo == "p":
                self.parrafo(b["texto"])
            elif tipo == "lista":
                self.lista(b["ordenada"], b["items"])
            elif tipo == "tabla":
                self.tabla(b["filas"])
            elif tipo == "destacado":
                self.destacado(b["texto"])
            elif tipo == "imagen":
                self.imagen(b["ruta"], b["pie"])
            elif tipo == "firma":
                self.firma(b["lineas"])
            elif tipo == "salto":
                self.salto_pendiente = True
        # evitar parrafo final vacio tras la ultima tabla
        return self

    def guarda(self, ruta_docx: Path, paginas: dict[str, int] | None):
        if self._marca_indice is not None:
            self._rellena_indice(paginas)
        self._activa_actualizar_campos()
        partes = {id(self.doc.element): self.doc.element, id(self.doc.styles.element): self.doc.styles.element}
        sec = self.doc.sections[0]
        for hf in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer, sec.even_page_header, sec.even_page_footer):
            if not hf.is_linked_to_previous:
                partes[id(hf._element)] = hf._element
        for raiz in partes.values():
            ordena_esquema(raiz)
        self.doc.save(str(ruta_docx))

    def _activa_actualizar_campos(self):
        settings = self.doc.settings.element
        if settings.find(qn("w:updateFields")) is not None:
            return
        uf = OxmlElement("w:updateFields"); uf.set(qn("w:val"), "true")
        posteriores = {"hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars", "rsids", "mathPr",
                       "attachedSchema", "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats",
                       "doNotAutoCompressPictures", "forceUpgrade", "captions", "readModeInkLockDown", "smartTagType",
                       "schemaLibrary", "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator"}
        for hijo in settings:
            if hijo.tag.split("}")[-1] in posteriores:
                hijo.addprevious(uf)
                return
        settings.append(uf)


# ---------------------------------------------------------------------------
# Conversion a PDF
# ---------------------------------------------------------------------------
def _conf_fuentes(tmp: Path) -> dict:
    """Si Microsoft YaHei UI no esta instalada, la sustituye por la sans mas parecida."""
    env = os.environ.copy()
    if shutil.which("fc-match"):
        res = subprocess.run(["fc-match", FUENTE], capture_output=True, text=True)
        if "YaHei" in res.stdout:
            return env
        conf = tmp / "fonts.conf"
        conf.write_text(f"""<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>
<alias binding="same"><family>{FUENTE}</family><prefer><family>{FUENTE_PDF_SUSTITUTA}</family><family>Carlito</family><family>DejaVu Sans</family></prefer></alias>
</fontconfig>""", encoding="utf-8")
        env["FONTCONFIG_FILE"] = str(conf)
        log.info("Fuente %s no instalada: en el PDF se usa %s.", FUENTE, FUENTE_PDF_SUSTITUTA)
    return env


def docx_a_pdf(ruta_docx: Path, carpeta_salida: Path) -> Path:
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    destino = carpeta_salida / (ruta_docx.stem + ".pdf")
    # 1) Windows con Word instalado: conversion nativa (fidelidad maxima)
    if sys.platform.startswith("win"):
        try:
            from docx2pdf import convert  # pip install docx2pdf
            convert(str(ruta_docx), str(destino))
            return destino
        except Exception as exc:  # noqa: BLE001
            log.warning("docx2pdf no disponible (%s). Se intenta LibreOffice.", exc)
    # 2) LibreOffice
    soffice = shutil.which("soffice") or shutil.which("libreoffice") or next(
        (str(r) for r in (Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
                          Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe")) if r.exists()), None)
    if not soffice:
        raise RuntimeError("No hay LibreOffice ni Word disponibles para generar el PDF.")
    with tempfile.TemporaryDirectory(prefix="mova_pdf_") as tmp:
        tmp_p = Path(tmp)
        env = _conf_fuentes(tmp_p)
        perfil = tmp_p / "perfil"
        env["SAL_USE_VCLPLUGIN"] = "svp"
        helper = Path("/mnt/skills/public/docx/scripts/office")
        if helper.exists():
            sys.path.insert(0, str(helper.parent))
            try:
                from office.soffice import get_soffice_env  # type: ignore
                shim_env = get_soffice_env()
                if "LD_PRELOAD" in shim_env:
                    env["LD_PRELOAD"] = shim_env["LD_PRELOAD"]
            except Exception:  # noqa: BLE001
                pass
        cmd = [soffice, f"-env:UserInstallation={perfil.as_uri()}", "--headless", "--convert-to", "pdf",
               "--outdir", str(carpeta_salida), str(ruta_docx)]
        res = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=240)
        if not destino.exists():
            raise RuntimeError(f"Fallo al convertir a PDF: {res.stderr or res.stdout}")
    return destino


def paginas_de_titulos(ruta_pdf: Path, titulos: list[dict]) -> dict[str, int]:
    from pypdf import PdfReader  # en vez de pdftotext, que no está instalado en los equipos
    brutas = [(pg.extract_text() or "") for pg in PdfReader(str(ruta_pdf)).pages]
    paginas = [normaliza_busqueda(pg) for pg in brutas]
    # paginas de portada/indice: contienen "INDICE" o varias lineas con puntos de relleno
    es_indice = [("INDICE" in paginas[i] and i < 4) or len(re.findall(r"\.{8,}", brutas[i])) >= 3
                 for i in range(len(brutas))]
    resultado: dict[str, int] = {}
    cursor = 0
    for i, flag in enumerate(es_indice[:6]):
        if flag:
            cursor = i + 1
    for t in titulos:
        clave = normaliza_busqueda(t["texto_indice"])
        for i in range(cursor, len(paginas)):
            if not es_indice[i] and clave in paginas[i]:
                resultado[t["marcador"]] = i + 1
                cursor = i
                break
    return resultado


# ---------------------------------------------------------------------------
def genera(entrada: Path, salida: Path, formato: str) -> list[Path]:
    meta, bloques = lee_entrada(entrada)
    salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_docx = salida.with_suffix(".docx")
    generados: list[Path] = []

    # Pasada 1: documento con indice sin paginas -> PDF para medir paginas
    gen = GeneradorInforme(meta, bloques, entrada.parent).construye()
    necesita_pdf = formato in ("pdf", "ambos")
    paginas = None
    with_indice = gen._marca_indice is not None
    if with_indice:
        with tempfile.TemporaryDirectory(prefix="mova_p1_") as tmp:
            prov = Path(tmp) / "provisional.docx"
            gen.guarda(prov, {t["marcador"]: 88 for t in gen.titulos})
            try:
                pdf_prov = docx_a_pdf(prov, Path(tmp))
                entradas = [t for t in gen.titulos if t["nivel"] <= 2]
                paginas = paginas_de_titulos(pdf_prov, entradas)
            except Exception as exc:  # noqa: BLE001
                log.warning("No se pudieron calcular las paginas del indice (%s). Word lo actualizara al abrir.", exc)
        gen = GeneradorInforme(meta, bloques, entrada.parent).construye()

    gen.guarda(ruta_docx, paginas)
    if formato in ("docx", "ambos"):
        generados.append(ruta_docx)
    if necesita_pdf:
        pdf = docx_a_pdf(ruta_docx, salida.parent)
        final_pdf = salida.with_suffix(".pdf")
        if pdf != final_pdf:
            shutil.move(pdf, final_pdf)
        generados.append(final_pdf)
        if formato == "pdf":
            ruta_docx.unlink(missing_ok=True)
    return generados


def main():
    ap = argparse.ArgumentParser(description="Genera informes con la identidad visual MOVA (Word/PDF).")
    ap.add_argument("entrada", type=Path, help="Fichero Markdown con el contenido")
    ap.add_argument("--salida", type=Path, required=True, help="Ruta de salida sin extension")
    ap.add_argument("--formato", choices=["docx", "pdf", "ambos"], default="ambos")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        for f in genera(args.entrada, args.salida, args.formato):
            print(f)
    except Exception as exc:  # noqa: BLE001
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
