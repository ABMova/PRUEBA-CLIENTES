"""Paleta MOVA (valores literales de la especificación) y generador de mova.qss.

Ejecutar `python -m ui.estilos.paleta` regenera ui/estilos/mova.qss.
Equivalencias: 1rem ≈ 13.6 px, de modo que 0.88rem ≈ 12 px.
"""
from __future__ import annotations

from pathlib import Path

PALETA = {
    "bg": "#0b0c0e", "card": "#141518", "card-2": "#1b1d21", "field": "#0f1013",
    "text": "#f3f4f6", "muted": "#9aa0a6", "gold": "#d9b45b", "gold-2": "#f0d98c",
    "gold-d": "#b8892f", "gold-txt": "#1a1405", "chip": "#241f12", "border": "#2a2d33",
    "ok": "#16a34a", "warn": "#d97706", "err": "#dc2626", "proc": "#3b82f6", "pend": "#6b7280",
}
RADIOS = {"r-card": 14, "r-box": 10, "r-btn": 8, "r-pill": 999}

REM = 13.6
FUENTE = '"Segoe UI", system-ui, Arial'
FUENTE_MONO = "Consolas, Menlo, monospace"
PX_BASE = round(0.88 * REM)        # 12 px
PX_APOYO = round(0.8 * REM)        # 11 px
PX_TITULO = round(1.4 * REM)       # 19 px
PX_NUMERO_PASO = round(1.25 * REM) # 17 px
PX_MARCA = round(0.55 * REM)       # 7 px

ESTADOS = ("pend", "proc", "ok", "warn", "err")


def generar_qss(p: dict = PALETA, r: dict = RADIOS) -> str:
    estados = "\n".join(
        f'QLabel#distintivo[estado="{e}"] {{ background: {p[e]}; }}' for e in ESTADOS)
    avisos = "\n".join(
        f'QFrame#aviso[gravedad="{e}"] {{ border: 1px solid {p[e]}; }}' for e in ESTADOS)
    return f"""/* Generado por ui/estilos/paleta.py: no editar a mano. */
QWidget {{
    color: {p['text']};
    font-family: {FUENTE};
    font-size: {PX_BASE}px;
}}
QMainWindow, QDialog, QWidget#raiz, QWidget#lienzo {{
    background: {p['bg']};
}}
QScrollArea {{ background: transparent; border: none; }}
QToolTip {{
    background: {p['card-2']}; color: {p['text']}; border: 1px solid {p['border']};
}}
QLabel {{ background: transparent; }}
QLabel[rol="apoyo"] {{ color: {p['muted']}; font-size: {PX_APOYO}px; }}
QLabel[rol="etiqueta"] {{ color: {p['muted']}; font-size: {PX_APOYO}px; }}
QLabel[rol="titulo-tarjeta"] {{ font-weight: 600; font-size: {PX_BASE + 1}px; }}
QLabel[pendiente="true"] {{ color: {p['warn']}; font-weight: 600; }}
QLabel#tituloApp {{ font-size: {PX_TITULO}px; font-weight: 600; }}
QLabel#subtituloApp {{ color: rgba(243, 244, 246, 0.82); font-size: {PX_BASE}px; }}
QLabel#marcaTitulo {{
    min-width: {PX_MARCA}px; max-width: {PX_MARCA}px;
    min-height: {PX_MARCA}px; max-height: {PX_MARCA}px;
    border-radius: 2px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['gold-2']}, stop:1 {p['gold-d']});
}}

/* Tarjetas */
QFrame#tarjeta {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['card-2']}, stop:1 {p['card']});
    border: 1px solid {p['border']};
    border-radius: {r['r-card']}px;
}}

/* Navegación por pasos */
QPushButton[rol="paso"] {{
    background: {p['card']}; border: 1px solid {p['border']}; color: {p['muted']};
    border-radius: {r['r-btn']}px; padding: 6px 10px; text-align: left;
}}
QPushButton[rol="paso"]:hover {{ border-color: {p['gold-d']}; }}
QPushButton[rol="paso"]:focus {{ border: 1px dashed {p['muted']}; }}
QPushButton[rol="paso"]:checked {{
    background: {p['chip']}; border: 1px solid {p['gold-d']}; color: {p['text']};
}}
QPushButton[rol="paso"]:disabled {{ color: {p['pend']}; }}
QLabel#numeroPaso {{
    min-width: {PX_NUMERO_PASO}px; max-width: {PX_NUMERO_PASO}px;
    min-height: {PX_NUMERO_PASO}px; max-height: {PX_NUMERO_PASO}px;
    border: 1px solid {p['border']}; border-radius: 4px; background: {p['field']};
    color: {p['muted']}; font-size: {PX_APOYO}px; font-weight: 600;
    qproperty-alignment: AlignCenter;
}}
QLabel#numeroPaso[activo="true"] {{
    background: {p['gold']}; color: {p['gold-txt']}; border-color: {p['gold-d']};
}}
QLabel#textoPaso {{ background: transparent; }}
QFrame#separadorVertical {{
    background: {p['border']}; min-width: 1px; max-width: 1px;
}}

/* Botones */
QPushButton {{
    background: {p['card']}; color: {p['text']}; border: 1px solid {p['border']};
    border-radius: {r['r-btn']}px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {p['gold-d']}; }}
QPushButton:pressed {{ background: {p['card-2']}; }}
QPushButton:disabled {{ color: {p['pend']}; border-color: {p['border']}; }}
QPushButton:focus {{ outline: none; border-color: {p['gold']}; }}
QPushButton[tipo="principal"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {p['gold-2']}, stop:1 {p['gold']});
    color: {p['gold-txt']}; border: 1px solid {p['gold-d']}; font-weight: 600;
}}
QPushButton[tipo="principal"]:hover {{ border-color: {p['gold-2']}; }}
QPushButton[tipo="principal"]:disabled {{
    background: {p['chip']}; color: {p['pend']}; border-color: {p['border']};
}}
QPushButton[tipo="destructivo"] {{
    background: transparent; color: {p['err']}; border: 1px solid {p['err']};
}}
QPushButton[tipo="destructivo"]:hover {{ background: rgba(220, 38, 38, 0.08); }}

/* Campos */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {{
    background: {p['field']}; color: {p['text']}; border: 1px solid {p['border']};
    border-radius: {r['r-btn']}px; padding: 4px 6px;
    selection-background-color: {p['gold-d']}; selection-color: {p['gold-txt']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QListWidget:focus {{ border: 1px solid {p['gold']}; }}
QPlainTextEdit[rol="mono"], QPlainTextEdit#registroVivo {{
    font-family: {FUENTE_MONO}; font-size: {PX_APOYO}px;
}}
QComboBox QAbstractItemView {{
    background: {p['field']}; color: {p['text']}; border: 1px solid {p['border']};
    selection-background-color: {p['chip']}; selection-color: {p['gold-2']};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QAbstractSpinBox {{ padding-left: 8px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 13px; height: 13px; border: 1px solid {p['border']}; background: {p['field']};
}}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {p['gold']}; border-color: {p['gold-d']};
}}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border-color: {p['gold']}; }}

/* Tablas */
QTableWidget, QTableView {{
    background: {p['field']}; alternate-background-color: {p['card']};
    gridline-color: {p['border']}; border: 1px solid {p['border']};
    border-radius: {r['r-box']}px;
    selection-background-color: {p['chip']}; selection-color: {p['gold-2']};
}}
QHeaderView::section {{
    background: {p['card-2']}; color: {p['muted']}; border: none;
    border-bottom: 1px solid {p['border']}; padding: 4px 6px; font-size: {PX_APOYO}px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {p['card-2']}; border: none; }}

/* Barras de desplazamiento */
QScrollBar:vertical {{ background: {p['bg']}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 24px; }}
QScrollBar:horizontal {{ background: {p['bg']}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* Distintivos en píldora */
QLabel#distintivo {{
    color: #ffffff; font-weight: 600; border-radius: 9px; padding: 1px 9px;
    font-size: {PX_APOYO}px;
}}
{estados}

/* Avisos */
QFrame#aviso {{ background: {p['chip']}; border-radius: {r['r-box']}px; }}
{avisos}
QFrame#avisoFlotante {{
    background: {p['chip']}; border: 1px solid {p['gold-d']}; border-radius: {r['r-box']}px;
}}
QFrame#avisoFlotante[gravedad="err"] {{ border-color: {p['err']}; }}
QFrame#avisoFlotante[gravedad="warn"] {{ border-color: {p['warn']}; }}
QFrame#avisoFlotante[gravedad="ok"] {{ border-color: {p['ok']}; }}

/* KPI */
QFrame#kpi {{
    background: {p['field']}; border: 1px solid {p['border']}; border-radius: {r['r-box']}px;
}}
QLabel#kpiValor {{ color: {p['gold']}; font-size: {round(2.0 * REM)}px; font-weight: 600; }}
QLabel#kpiValor[pendiente="true"] {{ color: {p['warn']}; font-size: {PX_BASE}px; }}

/* Barra de progreso */
QProgressBar {{
    background: {p['field']}; border: 1px solid {p['border']}; border-radius: 5px;
    min-height: 10px; max-height: 10px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {p['gold-d']}, stop:0.5 {p['gold']}, stop:1 {p['gold-2']});
}}

/* Zona de arrastre */
QFrame#zonaArrastre {{
    background: {p['field']}; border: 1px dashed {p['border']}; border-radius: {r['r-box']}px;
}}
QFrame#zonaArrastre[activa="true"] {{ border-color: {p['gold']}; }}

QMessageBox {{ background: {p['card']}; }}
QMessageBox QLabel {{ color: {p['text']}; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['border']}; }}
QMenu::item:selected {{ background: {p['chip']}; color: {p['gold-2']}; }}
"""


def ruta_qss() -> Path:
    return Path(__file__).resolve().parent / "mova.qss"


def escribir_qss(ruta: Path | None = None) -> Path:
    ruta = ruta or ruta_qss()
    ruta.write_text(generar_qss(), encoding="utf-8")
    return ruta


if __name__ == "__main__":
    print(escribir_qss())
