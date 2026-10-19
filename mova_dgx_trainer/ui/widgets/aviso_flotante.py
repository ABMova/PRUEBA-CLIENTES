"""Aviso flotante abajo a la derecha (sin animaciones)."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class AvisoFlotante(QFrame):
    MARGEN = 18

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("avisoFlotante")
        capa = QHBoxLayout(self)
        capa.setContentsMargins(14, 10, 14, 10)
        self.texto = QLabel()
        self.texto.setWordWrap(True)
        self.texto.setMaximumWidth(380)
        capa.addWidget(self.texto)
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.timeout.connect(self.hide)
        self.hide()

    def mostrar(self, texto: str, gravedad: str = "ok", ms: int = 4500) -> None:
        self.setProperty("gravedad", gravedad)
        self.style().unpolish(self)
        self.style().polish(self)
        self.texto.setText(texto)
        self.adjustSize()
        self.recolocar()
        self.show()
        self.raise_()
        self._temporizador.start(ms)

    def recolocar(self) -> None:
        padre = self.parentWidget()
        if padre is None:
            return
        self.move(padre.width() - self.width() - self.MARGEN,
                  padre.height() - self.height() - self.MARGEN)
