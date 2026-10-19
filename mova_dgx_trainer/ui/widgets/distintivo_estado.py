"""Distintivo en píldora: pend gris, proc azul, ok verde, warn ámbar, err rojo."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

# estado de dominio -> (estado visual, texto)
EQUIVALENCIAS = {
    "ok": ("ok", "ok"), "aprobado": ("ok", "aprobado"), "importado": ("ok", "importado"),
    "avisos": ("warn", "con avisos"), "insuficiente": ("warn", "insuficiente"),
    "warn": ("warn", "aviso"), "interrumpida": ("warn", "interrumpida"),
    "cancelada": ("warn", "cancelada"),
    "error": ("err", "error"), "err": ("err", "bloquea"), "descartado": ("err", "descartado"),
    "en_curso": ("proc", "en curso"), "proc": ("proc", "en curso"),
    "pend": ("pend", "pendiente"), None: ("pend", "pendiente"), "": ("pend", "pendiente"),
}


class Distintivo(QLabel):
    def __init__(self, estado: str | None = "pend", texto: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("distintivo")
        self.setAlignment(Qt.AlignCenter)
        self.fijar(estado, texto)

    def fijar(self, estado: str | None, texto: str | None = None) -> None:
        visual, por_defecto = EQUIVALENCIAS.get(estado, ("pend", str(estado)))
        self.setProperty("estado", visual)
        self.setText(texto or por_defecto)
        self.style().unpolish(self)
        self.style().polish(self)
