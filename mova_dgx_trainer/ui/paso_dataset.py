"""Paso 3 · Dataset: objetivo, limpieza, codificación, escalado, división y línea base."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QSpinBox)

from nucleo.preparador import ConfigPreparacion
from nucleo.rejillas import es_clasificacion
from ui.paso_base import PanelTrabajo, PasoBase
from ui.widgets.comun import boton, campo, etiqueta
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta


def _combo(opciones: list[tuple[str, str]]) -> QComboBox:
    c = QComboBox()
    for texto, valor in opciones:
        c.addItem(texto, valor)
    return c


class PasoDataset(PasoBase):
    titulo = "Dataset"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        fila = QHBoxLayout()
        fila.setSpacing(12)

        cfg = Tarjeta("Preparación", "La codificación y el escalado se ajustan solo con train "
                                     "dentro del script, para no filtrar información.")
        rejilla = QGridLayout()
        rejilla.setSpacing(8)
        self.objetivo = QComboBox()
        self.texto = QComboBox()
        self.excluidas = QListWidget()
        self.excluidas.setMinimumHeight(120)
        self.duplicados = QCheckBox("Eliminar filas duplicadas")
        self.duplicados.setChecked(True)
        self.constantes = QCheckBox("Descartar columnas constantes")
        self.constantes.setChecked(True)
        self.imp_num = _combo([("Mediana", "mediana"), ("Media", "media"), ("Cero", "cero")])
        self.imp_cat = _combo([("Moda", "moda"), ("Valor «desconocido»", "constante")])
        self.escalado = _combo([("Estandarización", "estandar"), ("Min-máx", "minmax"),
                                ("Sin escalado", "ninguno")])
        self.codificacion = _combo([("One-hot", "onehot"), ("Ordinal", "ordinal")])
        self.max_cat = QSpinBox()
        self.max_cat.setRange(2, 1000)
        self.max_cat.setValue(50)
        self.p_train, self.p_val, self.p_test = QSpinBox(), QSpinBox(), QSpinBox()
        for s, v in ((self.p_train, 70), (self.p_val, 15), (self.p_test, 15)):
            s.setRange(1, 98)
            s.setSuffix(" %")
            s.setValue(v)
        self.semilla = QSpinBox()
        self.semilla.setRange(0, 2_147_483_647)
        self.semilla.setValue(42)
        self.estratificar = QCheckBox("Estratificar por la clase (clasificación)")
        self.estratificar.setChecked(True)

        rejilla.addWidget(campo("Columna objetivo", self.objetivo), 0, 0)
        rejilla.addWidget(campo("Columna de texto (clasificación de texto)", self.texto), 0, 1)
        rejilla.addWidget(campo("Imputación numérica", self.imp_num), 1, 0)
        rejilla.addWidget(campo("Imputación categórica", self.imp_cat), 1, 1)
        rejilla.addWidget(campo("Escalado", self.escalado), 2, 0)
        rejilla.addWidget(campo("Codificación categórica", self.codificacion), 2, 1)
        rejilla.addWidget(campo("Máximo de categorías", self.max_cat), 3, 0)
        rejilla.addWidget(campo("Semilla", self.semilla), 3, 1)
        division = QHBoxLayout()
        division.addWidget(campo("Train", self.p_train))
        division.addWidget(campo("Validación", self.p_val))
        division.addWidget(campo("Test", self.p_test))
        rejilla.addLayout(division, 4, 0, 1, 2)
        cfg.anadir(rejilla)
        cfg.anadir(self.duplicados)
        cfg.anadir(self.constantes)
        cfg.anadir(self.estratificar)
        self.preparar_btn = boton("Preparar dataset", "principal", self._preparar)
        cfg.anadir(self.preparar_btn)
        fila.addWidget(cfg, 3)

        cols = Tarjeta("Columnas", "Marque las columnas que NO deben usarse para entrenar "
                                   "(identificadores, fugas del objetivo…).")
        cols.anadir(campo("Columnas excluidas", self.excluidas), 1)
        self.tabla_cols = TablaExportable(["Columna", "Tipo", "% nulos", "Únicos", "Nivel"],
                                          coord.exportar_tabla, "columnas", alto_minimo=180)
        cols.anadir(self.tabla_cols, 2)
        fila.addWidget(cols, 2)
        self.capa.addLayout(fila)

        self.panel = PanelTrabajo("Progreso de la preparación", 90)
        self.capa.addWidget(self.panel)

        res = Tarjeta("División y línea base",
                      "La línea base (DummyClassifier más frecuente o DummyRegressor media) se "
                      "calcula siempre sobre el mismo split y se guarda.")
        self.info = etiqueta("Aún no se ha preparado el dataset.", "apoyo")
        res.anadir(self.info)
        self.tabla_base = TablaExportable(["Métrica", "Línea base (test)"], coord.exportar_tabla,
                                          "linea_base", alto_minimo=150)
        res.anadir(self.tabla_base)
        self.capa.addWidget(res)

    def al_mostrar(self) -> None:
        if not self.pid:
            return
        p = self.servicio(self.coord.proyecto, self.pid)
        if not p:
            return
        tipo = p["tipo_tarea"]
        columnas = self.coord.columnas_brutas(self.pid)
        previo = self.objetivo.currentText()
        self.objetivo.clear()
        self.objetivo.addItems(columnas)
        if previo in columnas:
            self.objetivo.setCurrentText(previo)
        elif columnas:
            self.objetivo.setCurrentIndex(len(columnas) - 1)
        self.texto.clear()
        self.texto.addItems(columnas)
        self.texto.setEnabled(tipo == "clasificacion_texto")
        if "texto" in columnas:
            self.texto.setCurrentText("texto")
        self.estratificar.setEnabled(es_clasificacion(tipo))
        marcadas = {self.excluidas.item(i).text() for i in range(self.excluidas.count())
                    if self.excluidas.item(i).checkState() == Qt.Checked}
        self.excluidas.clear()
        for c in columnas:
            item = QListWidgetItem(c)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if c in marcadas else Qt.Unchecked)
            self.excluidas.addItem(item)
        val = self.coord.validacion_bruta(self.pid)
        self.tabla_cols.cargar([[f["columna"], f["tipo"], f"{f['nulos_pct']:.1f}", f["unicos"],
                                 f["nivel"]] for f in val], val, None, {4: lambda v: v})
        self._pintar_base()

    def _config(self) -> ConfigPreparacion:
        excluidas = [self.excluidas.item(i).text() for i in range(self.excluidas.count())
                     if self.excluidas.item(i).checkState() == Qt.Checked]
        total = self.p_train.value() + self.p_val.value() + self.p_test.value()
        return ConfigPreparacion(
            objetivo=self.objetivo.currentText(),
            columna_texto=self.texto.currentText() if self.texto.isEnabled() else "",
            columnas_excluidas=excluidas, eliminar_duplicados=self.duplicados.isChecked(),
            eliminar_constantes=self.constantes.isChecked(),
            imputacion_numerica=self.imp_num.currentData(),
            imputacion_categorica=self.imp_cat.currentData(),
            escalado=self.escalado.currentData(), codificacion=self.codificacion.currentData(),
            max_categorias=self.max_cat.value(),
            proporciones=(self.p_train.value() / total, self.p_val.value() / total,
                          self.p_test.value() / total),
            semilla=self.semilla.value(), estratificar=self.estratificar.isChecked())

    def _preparar(self) -> None:
        if not self.pid:
            self.estado_ui.avisar("Abra o cree un proyecto primero.", "warn")
            return
        if self.p_train.value() + self.p_val.value() + self.p_test.value() != 100:
            self.estado_ui.avisar("La división debe sumar 100 %.", "warn")
            return
        self.lanzar(self.coord.preparar, self.pid, self._config(), panel=self.panel,
                    al_terminar=self._al_preparar, botones=[self.preparar_btn])

    def _al_preparar(self, r: dict) -> None:
        self._pintar_base()
        self.estado_ui.avisar("Dataset preparado y línea base guardada. Siguiente: Entrenamiento.")
        self.estado_ui.datos_cambiados.emit()

    def _pintar_base(self) -> None:
        ds = self.coord.dataset_preparado(self.pid) if self.pid else None
        if not ds:
            self.info.setText("Aún no se ha preparado el dataset.")
            self.tabla_base.cargar([])
            return
        div = ds.get("division") or {}
        avisos = (ds.get("preparacion") or {}).get("avisos") or []
        self.info.setText(
            f"División {div.get('filas')} · estratificada: "
            f"{'sí' if div.get('estratificada') else 'no'} · semilla {div.get('semilla')} · "
            f"hash {ds['hash'][:16]}…" + (f"\nAvisos: {' · '.join(avisos)}" if avisos else ""))
        base = self.coord.linea_base(self.pid)
        filas = [[k, f"{v:.4f}" if isinstance(v, float) else v] for k, v in base.items()
                 if k != "matriz_confusion"]
        self.tabla_base.cargar(filas)
