"""Tabla de solo lectura con exportación a Excel/CSV de lo que se ve."""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ui.estilos.paleta import PALETA
from ui.widgets.distintivo_estado import Distintivo

COLOR_NIVEL = {"warn": PALETA["warn"], "err": PALETA["err"], "pend": PALETA["warn"]}


class Tabla(QTableWidget):
    def __init__(self, cabecera: list[str], parent=None, alto_minimo: int = 160):
        super().__init__(0, len(cabecera), parent)
        self.setHorizontalHeaderLabels(cabecera)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(26)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(alto_minimo)
        self._datos: list = []

    def cabecera(self) -> list[str]:
        return [self.horizontalHeaderItem(i).text() for i in range(self.columnCount())]

    def cargar(self, filas: list[list], datos: list | None = None,
               niveles: dict[tuple[int, int], str] | None = None,
               distintivos: dict[int, Callable[[object], str | None]] | None = None) -> None:
        """filas: valores; niveles {(fila, col): warn|err} pinta en color;
        distintivos {col: f(valor)->estado} pone una píldora en esa columna."""
        self.setRowCount(0)
        self._datos = list(datos or [])
        self.setRowCount(len(filas))
        for i, fila in enumerate(filas):
            for j, valor in enumerate(fila):
                texto = "" if valor is None else str(valor)
                if distintivos and j in distintivos:
                    d = Distintivo(distintivos[j](valor), texto or None)
                    contenedor = QWidget()
                    capa = QHBoxLayout(contenedor)
                    capa.setContentsMargins(4, 2, 4, 2)
                    capa.addWidget(d)
                    capa.addStretch(1)
                    self.setCellWidget(i, j, contenedor)
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                nivel = (niveles or {}).get((i, j))
                if nivel in COLOR_NIVEL or "[PENDIENTE" in texto:
                    item.setForeground(QColor(COLOR_NIVEL.get(nivel, PALETA["warn"])))
                if distintivos and j in distintivos:
                    item.setForeground(QColor(0, 0, 0, 0))
                self.setItem(i, j, item)
        self.resizeColumnsToContents()
        for j in range(self.columnCount()):
            self.setColumnWidth(j, min(self.columnWidth(j) + 12, 360))

    def dato_seleccionado(self):
        filas = self.selectionModel().selectedRows()
        if not filas or not self._datos:
            return None
        i = filas[0].row()
        return self._datos[i] if i < len(self._datos) else None

    def valores_visibles(self) -> list[list[str]]:
        filas = []
        for i in range(self.rowCount()):
            if self.isRowHidden(i):
                continue
            filas.append([(self.item(i, j).text() if self.item(i, j) else "")
                          for j in range(self.columnCount())])
        return filas


class TablaExportable(QWidget):
    """Tabla + botón «Exportar» (Excel o CSV). La escritura la hace el servicio."""

    def __init__(self, cabecera: list[str], exportar: Callable[[list, list, str], object],
                 nombre_base: str = "tabla", parent=None, alto_minimo: int = 160):
        super().__init__(parent)
        self._exportar, self._nombre = exportar, nombre_base
        self.tabla = Tabla(cabecera, alto_minimo=alto_minimo)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        capa.addWidget(self.tabla)
        barra = QHBoxLayout()
        barra.addStretch(1)
        self.boton_exportar = QPushButton("Exportar a Excel/CSV")
        self.boton_exportar.clicked.connect(self._al_exportar)
        barra.addWidget(self.boton_exportar)
        capa.addLayout(barra)

    def _al_exportar(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar tabla", f"{self._nombre}.xlsx",
            "Excel (*.xlsx);;CSV separado por punto y coma (*.csv)")
        if not ruta:
            return
        from ui.widgets.comun import mostrar_error
        try:
            self._exportar(self.tabla.cabecera(), self.tabla.valores_visibles(), ruta)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("Exportando tabla")
            mostrar_error(self, f"No se pudo exportar la tabla ({e})",
                          "Compruebe que el fichero no está abierto en otro programa")
            return
        ventana = self.window()
        if hasattr(ventana, "avisar"):
            ventana.avisar(f"Tabla exportada: {ruta}")

    def cargar(self, *args, **kwargs) -> None:
        self.tabla.cargar(*args, **kwargs)

    def dato_seleccionado(self):
        return self.tabla.dato_seleccionado()
