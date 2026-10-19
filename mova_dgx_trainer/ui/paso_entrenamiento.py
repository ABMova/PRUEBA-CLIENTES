"""Paso 4 · Entrenamiento en la DGX Spark (o en local) con logs en vivo y reintentos."""
from __future__ import annotations

import json

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout,
                               QPlainTextEdit, QSpinBox)

from nucleo.entrenador import FRAMEWORKS
from nucleo.rejillas import es_clasificacion
from ui.paso_base import PanelTrabajo, PasoBase
from ui.widgets.comun import boton, campo, etiqueta, etiqueta_pendiente
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta


class PasoEntrenamiento(PasoBase):
    titulo = "Entrenamiento"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        self._tipo = None
        fila = QHBoxLayout()
        fila.setSpacing(12)

        cfg = Tarjeta("Configuración", "Cada intento y cada reintento quedan como una ejecución "
                                       "nueva; nunca se sobrescribe la anterior.")
        rejilla = QGridLayout()
        rejilla.setSpacing(8)
        self.framework = QComboBox()
        for clave, f in FRAMEWORKS.items():
            self.framework.addItem(f["etiqueta"], clave)
        self.framework.currentIndexChanged.connect(self._iniciales)
        self.metrica = QComboBox()
        self.umbral_a = QDoubleSpinBox()
        self.umbral_b = QDoubleSpinBox()
        for s in (self.umbral_a, self.umbral_b):
            s.setDecimals(3)
            s.setSingleStep(0.01)
            s.setRange(0, 1000)
        self.lbl_a, self.lbl_b = etiqueta(""), etiqueta("")
        self.reintentos = QSpinBox()
        self.reintentos.setRange(0, 10)
        self.reintentos.setValue(3)
        self.semilla = QSpinBox()
        self.semilla.setRange(0, 2_147_483_647)
        self.semilla.setValue(42)
        rejilla.addWidget(campo("Framework", self.framework), 0, 0)
        rejilla.addWidget(campo("Métrica objetivo", self.metrica), 0, 1)
        caja_a, caja_b = QGridLayout(), QGridLayout()
        caja_a.addWidget(self.lbl_a, 0, 0)
        caja_a.addWidget(self.umbral_a, 1, 0)
        caja_b.addWidget(self.lbl_b, 0, 0)
        caja_b.addWidget(self.umbral_b, 1, 0)
        rejilla.addLayout(caja_a, 1, 0)
        rejilla.addLayout(caja_b, 1, 1)
        rejilla.addWidget(campo("Máximo de reintentos (0 los desactiva)", self.reintentos), 2, 0)
        rejilla.addWidget(campo("Semilla", self.semilla), 2, 1)
        cfg.anadir(rejilla)
        cfg.anadir(etiqueta_pendiente("decidir qué frameworks se soportan; PyTorch y TensorFlow "
                                      "no están verificados"))
        cfg.anadir(etiqueta_pendiente("métricas prioritarias por proyecto"))
        self.modo = etiqueta("", "apoyo")
        cfg.anadir(self.modo)
        self.lanzar_btn = boton("Lanzar entrenamiento", "principal", self._lanzar)
        cfg.anadir(self.lanzar_btn)
        cfg.capa.addStretch(1)
        fila.addWidget(cfg, 3)

        hp = Tarjeta("Hiperparámetros (JSON)", "Ante desempeño insuficiente se recorre la rejilla "
                                               "de nucleo/rejillas.py.")
        self.hp = QPlainTextEdit()
        self.hp.setProperty("rol", "mono")
        self.hp.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.hp.setMinimumHeight(170)
        hp.anadir(self.hp, 1)
        hp.anadir(boton("Valores iniciales", al_pulsar=self._iniciales))
        fila.addWidget(hp, 2)
        self.capa.addLayout(fila)

        self.panel = PanelTrabajo("Registro en vivo", 200)
        self.progreso = etiqueta("", "apoyo")
        self.panel.anadir(self.progreso)
        self.capa.addWidget(self.panel)

        ej = Tarjeta("Ejecuciones de este proyecto")
        self.tabla = TablaExportable(["Id", "Intento", "Motivo", "Estado", "Veredicto", "Modo",
                                      "Duración (s)", "Hiperparámetros"],
                                     coord.exportar_tabla, "ejecuciones")
        ej.anadir(self.tabla)
        self.capa.addWidget(ej)

    def al_mostrar(self) -> None:
        if not self.pid:
            return
        p = self.servicio(self.coord.proyecto, self.pid)
        if not p:
            return
        if p["tipo_tarea"] != self._tipo:
            self._tipo = p["tipo_tarea"]
            self.metrica.clear()
            self.metrica.addItems(self.coord.metricas_objetivo(self._tipo))
            u = self.coord.umbrales_por_defecto(self._tipo)
            if es_clasificacion(self._tipo):
                self.lbl_a.setText("Mínimo de la métrica objetivo")
                self.lbl_b.setText("Margen sobre la línea base")
                self.umbral_a.setValue(u["minimo"])
                self.umbral_b.setValue(u["margen_baseline"])
            else:
                self.lbl_a.setText("R² mínimo")
                self.lbl_b.setText("MAE máximo (factor × MAE de la línea base)")
                self.umbral_a.setValue(u["r2_minimo"])
                self.umbral_b.setValue(u["factor_mae"])
            self.metrica.setEnabled(es_clasificacion(self._tipo))
            cfg = self.coord.ultima_configuracion(self.pid)
            if cfg:
                self.framework.setCurrentIndex(max(0, self.framework.findData(cfg["framework"])))
                self.hp.setPlainText(json.dumps(cfg["hiperparametros"], indent=2,
                                                ensure_ascii=False))
                self.reintentos.setValue(cfg["max_reintentos"])
                self.semilla.setValue(cfg["semilla"])
            else:
                self._iniciales()
        ds = self.coord.dataset_preparado(self.pid)
        if ds:
            semilla = ((ds.get("preparacion") or {}).get("config") or {}).get("semilla")
            if semilla is not None and not self.ocupado():
                self.semilla.setValue(int(semilla))
        conexion = self.coord.cargar_conexion()
        destino = ("local" if conexion.get("modo") != "remoto"
                   else f"remoto por SSH ({conexion.get('usuario') or '?'}@"
                        f"{conexion.get('host') or '?'})")
        self.modo.setText(f"Modo de ejecución: {destino}. Se cambia en Configuración.")
        self._pintar_ejecuciones()

    def _iniciales(self, *_args) -> None:
        if not self._tipo:
            return
        hp = self.coord.hiperparametros_iniciales(self._tipo, self.framework.currentData())
        self.hp.setPlainText(json.dumps(hp, indent=2, ensure_ascii=False))

    def _pintar_ejecuciones(self) -> None:
        ejecuciones = self.coord.ejecuciones(self.pid) if self.pid else []
        filas = [[e["id"], e["intento"], e["motivo"], e["estado"], e["veredicto"] or "",
                  e["modo"], f"{e['duracion_s']:.1f}" if e["duracion_s"] else "",
                  json.dumps(e["hiperparametros"], ensure_ascii=False)] for e in ejecuciones]
        self.tabla.cargar(filas, ejecuciones, None,
                          {3: lambda v: v, 4: lambda v: v or "pend"})

    def _lanzar(self) -> None:
        if not self.pid:
            self.estado_ui.avisar("Abra o cree un proyecto primero.", "warn")
            return
        try:
            hp = json.loads(self.hp.toPlainText() or "{}")
        except ValueError as e:
            from ui.widgets.comun import mostrar_error
            mostrar_error(self, f"El JSON de hiperparámetros no es válido ({e.msg}, línea {e.lineno})",
                          "Corríjalo o pulse «Valores iniciales»")
            return
        if es_clasificacion(self._tipo):
            umbrales = {"minimo": self.umbral_a.value(), "margen_baseline": self.umbral_b.value()}
        else:
            umbrales = {"r2_minimo": self.umbral_a.value(), "factor_mae": self.umbral_b.value()}
        cfg_id = self.servicio(self.coord.guardar_configuracion, self.pid,
                               self.framework.currentData(), hp, umbrales,
                               self.metrica.currentText() or "r2", self.reintentos.value(),
                               self.semilla.value())
        if cfg_id is None:
            return
        self.panel.registro.limpiar()
        self.lanzar(self.coord.entrenar, self.pid, cfg_id, panel=self.panel,
                    al_terminar=self._al_terminar, botones=[self.lanzar_btn],
                    al_evento=self._al_evento)

    def _al_evento(self, e: dict) -> None:
        if e.get("evento") == "progreso":
            partes = [f"Época {e.get('epoca')}/{e.get('total')}"]
            if e.get("perdida") is not None:
                partes.append(f"pérdida {float(e['perdida']):.4f}")
            if e.get("metrica") is not None:
                partes.append(f"métrica {float(e['metrica']):.4f}")
            self.progreso.setText(" · ".join(partes))
        elif e.get("evento") in ("ejecucion", "fin_ejecucion"):
            self._pintar_ejecuciones()

    def _al_terminar(self, r: dict) -> None:
        self._pintar_ejecuciones()
        ver = r.get("veredicto")
        self.estado_ui.avisar(f"Entrenamiento terminado: {r.get('ejecuciones')} ejecución(es), "
                              f"veredicto {ver}.", "ok" if ver == "aprobado" else "warn")
        self.estado_ui.datos_cambiados.emit()
