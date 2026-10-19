"""Paso 6 · Informe final en Word y PDF con resultados, gráficas y trazabilidad."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout

from ui.paso_base import PanelTrabajo, PasoBase
from ui.widgets.comun import boton, etiqueta
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta

SECCIONES = ("Portada · Resumen con KPIs · Línea base · Dataset y procedencia · Configuración e "
             "hiperparámetros · Ejecuciones y reintentos con veredicto · Gráficas · Anexo de "
             "trazabilidad (semilla, hashes, versiones, comando, log)")


class PasoInforme(PasoBase):
    titulo = "Informe"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        contenido = Tarjeta("Informe final", "Word y PDF con el mismo contenido. Lo que falte se "
                                             "marca como [PENDIENTE: dato].")
        contenido.anadir(etiqueta(SECCIONES, "apoyo"))
        self.estado_lbl = etiqueta("", "apoyo")
        contenido.anadir(self.estado_lbl)
        self.generar = boton("Generar informe Word y PDF", "principal", self._generar)
        contenido.anadir(self.generar)
        self.capa.addWidget(contenido)

        self.panel = PanelTrabajo("Progreso del informe", 90)
        self.capa.addWidget(self.panel)

        lista = Tarjeta("Informes generados")
        self.tabla = TablaExportable(["Fecha", "Word", "PDF"], coord.exportar_tabla, "informes")
        lista.anadir(self.tabla)
        acciones = QHBoxLayout()
        acciones.addWidget(boton("Abrir Word", al_pulsar=lambda: self._abrir("ruta_docx")))
        acciones.addWidget(boton("Abrir PDF", al_pulsar=lambda: self._abrir("ruta_pdf")))
        acciones.addWidget(boton("Abrir carpeta", al_pulsar=lambda: self._abrir("carpeta")))
        acciones.addStretch(1)
        lista.anadir(acciones)
        self.capa.addWidget(lista)
        self.capa.addStretch(1)

    def al_mostrar(self) -> None:
        if not self.pid:
            return
        r = self.servicio(self.coord.resumen_resultados, self.pid)
        if r:
            n = len(r["ejecuciones"])
            self.estado_lbl.setText(f"{n} ejecución(es) registradas; mejor: "
                                    f"{'#' + str(r['mejor']['id']) if r['mejor'] else '[PENDIENTE: ninguna correcta]'}.")
        informes = self.coord.informes(self.pid)
        self.tabla.cargar([[i["creado"], Path(i["ruta_docx"]).name, Path(i["ruta_pdf"]).name]
                           for i in informes], informes)

    def _generar(self) -> None:
        if not self.pid:
            self.estado_ui.avisar("Abra o cree un proyecto primero.", "warn")
            return
        self.lanzar(self.coord.exportar_informe, self.pid, panel=self.panel,
                    al_terminar=self._al_generar, botones=[self.generar])

    def _al_generar(self, r: dict) -> None:
        self.al_mostrar()
        self.estado_ui.avisar(f"Informe generado: {Path(r['docx']).name} y {Path(r['pdf']).name}.")

    def _abrir(self, clave: str) -> None:
        i = self.tabla.dato_seleccionado() or (self.coord.informes(self.pid) or [None])[0]
        if not i:
            self.estado_ui.avisar("Todavía no hay informes.", "warn")
            return
        ruta = Path(i["ruta_docx"]).parent if clave == "carpeta" else Path(i[clave])
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))
