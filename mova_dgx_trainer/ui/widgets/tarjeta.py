"""Tarjeta (QFrame#tarjeta) con título precedido de un cuadradito dorado."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Tarjeta(QFrame):
    def __init__(self, titulo: str = "", subtitulo: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(14, 12, 14, 14)
        self.capa.setSpacing(8)
        if titulo:
            cabecera = QHBoxLayout()
            cabecera.setSpacing(8)
            marca = QLabel()
            marca.setObjectName("marcaTitulo")
            self.titulo = QLabel(titulo)
            self.titulo.setProperty("rol", "titulo-tarjeta")
            cabecera.addWidget(marca)
            cabecera.addWidget(self.titulo)
            cabecera.addStretch(1)
            self.cabecera = cabecera
            self.capa.addLayout(cabecera)
        if subtitulo:
            apoyo = QLabel(subtitulo)
            apoyo.setProperty("rol", "apoyo")
            apoyo.setWordWrap(True)
            self.capa.addWidget(apoyo)

    def anadir(self, widget_o_capa, estirar: int = 0):
        if isinstance(widget_o_capa, QWidget):
            self.capa.addWidget(widget_o_capa, estirar)
        else:
            self.capa.addLayout(widget_o_capa, estirar)
        return widget_o_capa

    def anadir_en_cabecera(self, widget: QWidget) -> None:
        self.cabecera.addWidget(widget)
