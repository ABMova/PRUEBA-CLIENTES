"""KPI: cifra grande en dorado sobre --field. Son las únicas cifras grandes."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from nucleo.contexto import pendiente


class Kpi(QFrame):
    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setObjectName("kpi")
        capa = QVBoxLayout(self)
        capa.setContentsMargins(12, 10, 12, 10)
        capa.setSpacing(2)
        self.titulo = QLabel(titulo)
        self.titulo.setProperty("rol", "etiqueta")
        self.valor = QLabel()
        self.valor.setObjectName("kpiValor")
        self.apoyo = QLabel("")
        self.apoyo.setProperty("rol", "apoyo")
        capa.addWidget(self.titulo)
        capa.addWidget(self.valor)
        capa.addWidget(self.apoyo)
        self.fijar(None, "dato")

    def fijar(self, texto: str | None, dato_pendiente: str = "dato", apoyo: str = "") -> None:
        vacio = texto is None or texto == ""
        self.valor.setText(pendiente(dato_pendiente) if vacio else texto)
        self.valor.setProperty("pendiente", "true" if vacio else "false")
        self.valor.style().unpolish(self.valor)
        self.valor.style().polish(self.valor)
        self.apoyo.setText(apoyo)


class RejillaKpi(QGridLayout):
    def __init__(self, titulos: list[str], columnas: int = 4):
        super().__init__()
        self.setSpacing(10)
        self.kpis = {}
        for i, t in enumerate(titulos):
            k = Kpi(t)
            self.kpis[t] = k
            self.addWidget(k, i // columnas, i % columnas)
