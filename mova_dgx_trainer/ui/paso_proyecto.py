"""Paso 1 · Proyecto: crear proyecto y tipo de tarea, o abrir uno existente."""
from __future__ import annotations

from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit

from nucleo.coordinador import PASOS
from ui.paso_base import PasoBase
from ui.widgets.comun import boton, campo, etiqueta, etiqueta_pendiente
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta

NOMBRES_PASO = {"proyecto": "1 Proyecto", "importacion": "2 Importación", "dataset": "3 Dataset",
                "entrenamiento": "4 Entrenamiento", "resultados": "5 Resultados",
                "informe": "6 Informe"}


class PasoProyecto(PasoBase):
    titulo = "Proyecto"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        fila = QHBoxLayout()
        fila.setSpacing(12)

        nuevo = Tarjeta("Nuevo proyecto", "Un proyecto agrupa datos, configuraciones, "
                                          "ejecuciones e informes.")
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("p. ej. Propensión de compra 2026")
        self.tipo = QComboBox()
        modelo: QStandardItemModel = self.tipo.model()
        for clave, texto, habilitado in coord.tipos_tarea():
            self.tipo.addItem(texto, clave)
            if not habilitado:
                modelo.item(self.tipo.count() - 1).setEnabled(False)
        self.descripcion = QPlainTextEdit()
        self.descripcion.setFixedHeight(64)
        nuevo.anadir(campo("Nombre", self.nombre))
        nuevo.anadir(campo("Tipo de tarea", self.tipo,
                           "El ajuste fino de LLM queda deshabilitado hasta confirmar su alcance."))
        nuevo.anadir(etiqueta_pendiente("confirmar alcance del ajuste fino de LLM"))
        nuevo.anadir(campo("Descripción (opcional)", self.descripcion))
        self.crear = boton("Crear proyecto", "principal", self._crear)
        nuevo.anadir(self.crear)
        nuevo.capa.addStretch(1)
        fila.addWidget(nuevo, 2)

        lista = Tarjeta("Proyectos", "Doble clic o «Abrir» para continuar donde se quedó.")
        self.tabla = TablaExportable(["Id", "Nombre", "Tipo", "Paso actual", "Actualizado"],
                                     coord.exportar_tabla, "proyectos", alto_minimo=260)
        self.tabla.tabla.doubleClicked.connect(lambda _i: self._abrir())
        lista.anadir(self.tabla, 1)
        botones = QHBoxLayout()
        botones.addWidget(boton("Abrir proyecto", al_pulsar=self._abrir))
        botones.addWidget(boton("Actualizar", al_pulsar=self.al_mostrar))
        botones.addStretch(1)
        lista.anadir(botones)
        self.activo = etiqueta("Ningún proyecto abierto.", "apoyo")
        lista.anadir(self.activo)
        fila.addWidget(lista, 3)
        self.capa.addLayout(fila)
        self.capa.addStretch(1)

    def al_mostrar(self) -> None:
        proyectos = self.servicio(self.coord.listar_proyectos) or []
        filas = [[p["id"], p["nombre"], p["tipo_tarea"],
                  NOMBRES_PASO.get((p.get("estado_pipeline") or {}).get("paso_actual"), "—"),
                  p["actualizado"]] for p in proyectos]
        self.tabla.cargar(filas, proyectos)
        if self.pid:
            p = next((x for x in proyectos if x["id"] == self.pid), None)
            if p:
                self.activo.setText(f"Proyecto abierto: {p['nombre']} ({p['tipo_tarea']}).")

    def _crear(self) -> None:
        pid = self.servicio(self.coord.crear_proyecto, self.nombre.text(),
                            self.tipo.currentData(), self.descripcion.toPlainText())
        if pid is None:
            return
        self.nombre.clear()
        self.descripcion.clear()
        self.estado_ui.avisar("Proyecto creado.")
        self.estado_ui.abrir(pid)
        self.estado_ui.ir_a.emit("importacion")

    def _abrir(self) -> None:
        p = self.tabla.dato_seleccionado()
        if not p:
            self.estado_ui.avisar("Seleccione un proyecto de la lista.", "warn")
            return
        self.estado_ui.abrir(p["id"])
        paso = (p.get("estado_pipeline") or {}).get("paso_actual") or "importacion"
        self.estado_ui.ir_a.emit(paso if paso in PASOS else "importacion")
