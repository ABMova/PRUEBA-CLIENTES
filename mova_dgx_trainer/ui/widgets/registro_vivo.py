"""Registro en vivo con hora, monoespaciado sobre --field."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class RegistroVivo(QPlainTextEdit):
    def __init__(self, parent=None, max_lineas: int = 5000, alto_minimo: int = 140):
        super().__init__(parent)
        self.setObjectName("registroVivo")
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lineas)
        self.setMinimumHeight(alto_minimo)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def anadir(self, texto: str) -> None:
        hora = datetime.now().strftime("%H:%M:%S")
        for linea in str(texto).splitlines() or [""]:
            self.appendPlainText(f"{hora}  {linea}")
        self.moveCursor(QTextCursor.End)

    def limpiar(self) -> None:
        self.clear()
