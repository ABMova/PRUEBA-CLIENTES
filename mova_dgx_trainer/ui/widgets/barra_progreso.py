"""Barra de progreso de 10 px con relleno en degradado dorado."""
from __future__ import annotations

from PySide6.QtWidgets import QProgressBar


class BarraProgreso(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(10)

    def reiniciar(self) -> None:
        self.setValue(0)
