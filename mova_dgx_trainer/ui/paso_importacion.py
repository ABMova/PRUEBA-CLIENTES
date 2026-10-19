"""Paso 2 · Importación en lote de Excel, CSV, TXT y JSON (ficheros o carpetas)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLineEdit, QListWidget, QMessageBox, QSpinBox, QVBoxLayout)

from nucleo.importador import EXTENSIONES, OpcionesImportacion
from ui.paso_base import PanelTrabajo, PasoBase
from ui.widgets.comun import boton, campo, etiqueta
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta

DELIMITADORES = [("Detectar", None), ("Coma ( , )", ","), ("Punto y coma ( ; )", ";"),
                 ("Tabulador", "\t"), ("Barra ( | )", "|")]
CODIFICACIONES = [("Detectar", None), ("utf-8", "utf-8"), ("utf-8-sig", "utf-8-sig"),
                  ("latin-1", "latin-1")]


class ZonaArrastre(QFrame):
    soltado = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("zonaArrastre")
        self.setAcceptDrops(True)
        self.setMinimumHeight(70)
        capa = QVBoxLayout(self)
        texto = etiqueta("Arrastre aquí ficheros o carpetas (Excel, CSV, TXT, JSON, JSONL)",
                         "apoyo")
        texto.setAlignment(Qt.AlignCenter)
        capa.addWidget(texto)

    def _activa(self, valor: bool) -> None:
        self.setProperty("activa", "true" if valor else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            self._activa(True)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):  # noqa: N802
        self._activa(False)

    def dropEvent(self, e):  # noqa: N802
        self._activa(False)
        rutas = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if rutas:
            self.soltado.emit(rutas)


class PasoImportacion(PasoBase):
    titulo = "Importación"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        fila = QHBoxLayout()
        fila.setSpacing(12)

        ficheros = Tarjeta("Ficheros", "Selección múltiple o carpetas completas. Un fichero que "
                                       "falla no detiene el lote.")
        self.zona = ZonaArrastre()
        self.zona.soltado.connect(self._anadir)
        ficheros.anadir(self.zona)
        self.lista = QListWidget()
        self.lista.setMinimumHeight(110)
        ficheros.anadir(self.lista, 1)
        botones = QHBoxLayout()
        botones.addWidget(boton("Añadir ficheros", al_pulsar=self._elegir_ficheros))
        botones.addWidget(boton("Añadir carpeta", al_pulsar=self._elegir_carpeta))
        botones.addWidget(boton("Quitar", al_pulsar=self._quitar))
        botones.addStretch(1)
        ficheros.anadir(botones)
        fila.addWidget(ficheros, 3)

        opciones = Tarjeta("Opciones de lectura", "Lo detectado se muestra en la tabla y se puede "
                                                  "corregir aquí y reimportar el fichero.")
        rejilla = QGridLayout()
        rejilla.setSpacing(8)
        self.codificacion = QComboBox()
        for t, v in CODIFICACIONES:
            self.codificacion.addItem(t, v)
        self.delimitador = QComboBox()
        for t, v in DELIMITADORES:
            self.delimitador.addItem(t, v)
        self.cabecera = QSpinBox()
        self.cabecera.setRange(0, 100)
        self.hojas = QLineEdit()
        self.hojas.setPlaceholderText("vacío = primera · * = todas · Hoja1, Hoja2")
        self.muestreo = QComboBox()
        self.muestreo.addItem("Primeras N filas", "primeras")
        self.muestreo.addItem("Aleatoria con semilla", "aleatoria")
        self.n_muestreo = QSpinBox()
        self.n_muestreo.setRange(1000, 50_000_000)
        self.n_muestreo.setSingleStep(10000)
        self.n_muestreo.setValue(200_000)
        self.semilla = QSpinBox()
        self.semilla.setRange(0, 2_147_483_647)
        self.semilla.setValue(42)
        rejilla.addWidget(campo("Codificación (CSV/TXT)", self.codificacion), 0, 0)
        rejilla.addWidget(campo("Delimitador (CSV/TXT)", self.delimitador), 0, 1)
        rejilla.addWidget(campo("Fila de cabecera", self.cabecera), 1, 0)
        rejilla.addWidget(campo("Hojas de Excel", self.hojas), 1, 1)
        rejilla.addWidget(campo("Muestreo (> 1 GB)", self.muestreo), 2, 0)
        rejilla.addWidget(campo("Filas de la muestra", self.n_muestreo), 2, 1)
        rejilla.addWidget(campo("Semilla del muestreo", self.semilla), 3, 0)
        opciones.anadir(rejilla)
        opciones.anadir(etiqueta("Más de 200 MB o 1.000.000 de filas: lectura por trozos de "
                                 "50.000 filas. Más de 1 GB: aviso y muestra.", "apoyo"))
        self.importar = boton("Importar lote", "principal", self._importar)
        opciones.anadir(self.importar)
        opciones.capa.addStretch(1)
        fila.addWidget(opciones, 2)
        self.capa.addLayout(fila)

        self.panel = PanelTrabajo("Progreso de la importación", 110)
        self.capa.addWidget(self.panel)

        resultado = Tarjeta("Resultado por fichero")
        self.resumen = etiqueta("Sin importar todavía.", "apoyo")
        resultado.anadir(self.resumen)
        self.tabla = TablaExportable(
            ["Fichero", "Estado", "Filas", "Columnas", "Codificación", "Delimitador", "Hoja",
             "Avisos / motivo"], coord.exportar_tabla, "importacion")
        resultado.anadir(self.tabla)
        acciones = QHBoxLayout()
        self.reimportar = boton("Reimportar seleccionado con estas opciones",
                                al_pulsar=self._reimportar)
        self.como_texto = boton("Importar JSON como texto", al_pulsar=self._como_texto)
        self.usar = boton("Usar estos datos en el proyecto", al_pulsar=self._confirmar)
        for b in (self.reimportar, self.como_texto, self.usar):
            acciones.addWidget(b)
        acciones.addStretch(1)
        resultado.anadir(acciones)
        self.capa.addWidget(resultado)

        validacion = Tarjeta("Validación del dataset combinado",
                             "Ámbar: revisar. Rojo: bloquea el paso siguiente.")
        self.validacion_resumen = etiqueta("", "apoyo")
        validacion.anadir(self.validacion_resumen)
        self.tabla_validacion = TablaExportable(
            ["Columna", "Tipo", "% nulos", "Valores únicos", "Constante", "Nivel"],
            coord.exportar_tabla, "validacion")
        validacion.anadir(self.tabla_validacion)
        self.capa.addWidget(validacion)

    # --- selección -------------------------------------------------------------
    def _rutas(self) -> list[str]:
        return [self.lista.item(i).text() for i in range(self.lista.count())]

    def _anadir(self, rutas: list[str]) -> None:
        actuales = set(self._rutas())
        for r in rutas:
            if r not in actuales:
                self.lista.addItem(r)

    def _elegir_ficheros(self) -> None:
        filtro = "Datos (" + " ".join(f"*{e}" for e in EXTENSIONES) + ")"
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegir ficheros", "", filtro)
        self._anadir(rutas)

    def _elegir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, "Elegir carpeta")
        if carpeta:
            self._anadir([carpeta])

    def _quitar(self) -> None:
        for item in self.lista.selectedItems():
            self.lista.takeItem(self.lista.row(item))

    def _opciones(self, **cambios) -> OpcionesImportacion:
        hojas_txt = self.hojas.text().strip()
        hojas = None
        if hojas_txt == "*":
            hojas = ["*"]
        elif hojas_txt:
            hojas = [h.strip() for h in hojas_txt.split(",") if h.strip()]
        o = OpcionesImportacion(codificacion=self.codificacion.currentData(),
                                delimitador=self.delimitador.currentData(),
                                hojas=hojas, fila_cabecera=self.cabecera.value(),
                                muestreo=self.muestreo.currentData(),
                                n_muestreo=self.n_muestreo.value(), semilla=self.semilla.value())
        for k, v in cambios.items():
            setattr(o, k, v)
        return o

    # --- acciones ----------------------------------------------------------------
    def _importar(self) -> None:
        if not self.pid:
            self.estado_ui.avisar("Abra o cree un proyecto primero.", "warn")
            return
        rutas = self._rutas()
        if not rutas:
            self.estado_ui.avisar("Añada ficheros o carpetas al lote.", "warn")
            return
        self.panel.registro.anadir(f"Lote de {len(rutas)} entrada(s).")
        self.lanzar(self.coord.importar, self.pid, rutas, self._opciones(), panel=self.panel,
                    al_terminar=self._al_importar,
                    botones=[self.importar, self.usar, self.reimportar])

    def _al_importar(self, resultado: dict) -> None:
        self._pintar_lote()
        resumen = resultado["resumen"]
        if not resumen.resultados:
            self.estado_ui.avisar(" ".join(resumen.avisos), "warn")
            return
        aviso = "warn" if resumen.descartados or resumen.avisos else "ok"
        self.estado_ui.avisar(" ".join([resumen.texto()] + resumen.avisos), aviso)

    def _pintar_lote(self) -> None:
        lote = self.coord.lote_actual(self.pid) if self.pid else None
        if not lote:
            self.tabla.cargar([])
            self.resumen.setText("Sin importar todavía.")
            return
        filas, niveles = [], {}
        for i, r in enumerate(lote.resultados):
            delim = {"\t": "tabulador", None: "—"}.get(r.delimitador, r.delimitador)
            avisos = r.error or "; ".join(r.avisos + [t for _, t in (
                r.validacion.problemas if r.validacion else [])])
            filas.append([r.nombre, r.estado, r.filas, r.columnas, r.codificacion or "—",
                          delim, r.hoja or "—", avisos])
            if r.estado == "descartado":
                niveles[(i, 7)] = "err"
            elif avisos:
                niveles[(i, 7)] = "warn"
        self.tabla.cargar(filas, lote.resultados, niveles, {1: lambda v: v})
        self.resumen.setText(lote.texto())

    def _reimportar(self, como_texto: bool = False) -> None:
        r = self.tabla.dato_seleccionado()
        if not r:
            self.estado_ui.avisar("Seleccione un fichero de la tabla.", "warn")
            return
        opciones = self._opciones(json_como_texto=como_texto)
        nuevo = self.servicio(self.coord.reimportar_fichero, self.pid, r.ruta, opciones)
        if nuevo:
            self._pintar_lote()
            self.estado_ui.avisar(f"{nuevo.nombre}: {nuevo.estado}.",
                                  "err" if nuevo.estado == "descartado" else "ok")

    def _como_texto(self) -> None:
        r = self.tabla.dato_seleccionado()
        if not r or not r.nodo_no_tabulable:
            self.estado_ui.avisar("Seleccione un JSON descartado por no ser tabulable.", "warn")
            return
        self._reimportar(como_texto=True)

    def _confirmar(self) -> None:
        if not self.pid:
            return
        compatible, dif = self.coord.comparar_lote(self.pid)
        estrategia = "compatible"
        if not compatible:
            estrategia = self._decidir_esquema(dif)
            if not estrategia:
                return
        r = self.servicio(self.coord.confirmar_importacion, self.pid, estrategia)
        if not r:
            return
        self._pintar_validacion(r["validacion"])
        self.validacion_resumen.setText(
            f"{r['filas']} filas × {r['columnas']} columnas · hash {r['hash'][:16]}…")
        self.estado_ui.avisar("Datos incorporados al proyecto. Siguiente: Dataset.")
        self.estado_ui.datos_cambiados.emit()

    def _decidir_esquema(self, dif: dict) -> str | None:
        lineas = []
        for nombre, d in dif.get("por_fichero", {}).items():
            lineas.append(f"• {nombre}: le faltan {', '.join(d['faltan'])}")
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Warning)
        caja.setWindowTitle("Esquemas distintos")
        caja.setText("Los ficheros no tienen las mismas columnas.\nElija cómo combinarlos.")
        caja.setInformativeText("\n".join(lineas[:15]) +
                                f"\n\nColumnas comunes: {', '.join(dif.get('comunes', [])) or 'ninguna'}")
        union = caja.addButton("Unión (rellena con vacíos)", QMessageBox.AcceptRole)
        inter = caja.addButton("Intersección (solo comunes)", QMessageBox.AcceptRole)
        caja.addButton("Cancelar", QMessageBox.RejectRole)
        caja.exec()
        if caja.clickedButton() is union:
            return "union"
        if caja.clickedButton() is inter:
            return "interseccion"
        return None

    def _pintar_validacion(self, filas_val: list[dict]) -> None:
        filas, niveles = [], {}
        for i, f in enumerate(filas_val):
            filas.append([f["columna"], f["tipo"], f"{f['nulos_pct']:.1f}", f["unicos"],
                          "sí" if f["constante"] else "no", f["nivel"]])
            if f["nivel"] in ("warn", "err"):
                niveles[(i, 2)] = f["nivel"]
        self.tabla_validacion.cargar(filas, filas_val, niveles, {5: lambda v: v})

    def al_mostrar(self) -> None:
        self._pintar_lote()
        if self.pid:
            val = self.coord.validacion_bruta(self.pid)
            self._pintar_validacion(val)
            if not val:
                self.validacion_resumen.setText("Aún no hay datos incorporados al proyecto.")
            else:
                ds = self.coord.dataset_bruto(self.pid)
                self.validacion_resumen.setText(
                    f"{ds['filas']} filas × {ds['columnas']} columnas · hash {ds['hash'][:16]}…")

