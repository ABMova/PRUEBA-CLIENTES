"""Configuración: modo de ejecución, conexión SSH cifrada, entorno, copias y tablas."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
                               QLineEdit, QRadioButton, QSpinBox)

from datos.esquema import TABLAS
from infra.ejecutor_ssh import interprete_local_por_defecto
from nucleo.contexto import pendiente
from ui.paso_base import PanelTrabajo, PasoBase
from ui.widgets.comun import boton, campo, confirmar, etiqueta, etiqueta_pendiente
from ui.widgets.tabla import TablaExportable
from ui.widgets.tarjeta import Tarjeta

DECISIONES_ABIERTAS = [
    "Qué frameworks soportar: scikit-learn verificado; PyTorch y TensorFlow no verificados.",
    "Métricas prioritarias: la métrica objetivo es configurable por ejecución.",
    "Ajuste genérico o específico por proyecto.",
    "Requisitos de versionado de modelos y datasets.",
    "Uso de SQLite: es una propuesta, no una petición.",
    "Alcance del ajuste fino de LLM (ver /opt/entrenamiento en la Spark).",
]


class PanelConfiguracion(PasoBase):
    titulo = "Configuración"

    def __init__(self, coord, estado, parent=None):
        super().__init__(coord, estado, parent)
        fila = QHBoxLayout()
        fila.setSpacing(12)

        conexion = Tarjeta("Ejecución", "Usuario, host y clave se guardan cifrados en el almacén "
                                        "de este equipo; nunca en el código.")
        modos = QHBoxLayout()
        self.local = QRadioButton("Local (este equipo)")
        self.remoto = QRadioButton("Remoto por SSH (DGX Spark)")
        grupo = QButtonGroup(self)
        grupo.addButton(self.local)
        grupo.addButton(self.remoto)
        self.local.setChecked(True)
        modos.addWidget(self.local)
        modos.addWidget(self.remoto)
        modos.addStretch(1)
        conexion.anadir(modos)
        rejilla = QGridLayout()
        rejilla.setSpacing(8)
        self.interprete_local = QLineEdit()
        self.interprete_local.setPlaceholderText(interprete_local_por_defecto() or
                                                 pendiente("intérprete de Python"))
        self.host = QLineEdit()
        self.host.setPlaceholderText("192.168.1.240")
        self.puerto = QSpinBox()
        self.puerto.setRange(1, 65535)
        self.puerto.setValue(22)
        self.usuario = QLineEdit()
        self.clave = QLineEdit()
        self.clave.setPlaceholderText("ruta a la clave privada (opcional)")
        self.contrasena = QLineEdit()
        self.contrasena.setEchoMode(QLineEdit.Password)
        self.contrasena.setPlaceholderText("opcional si hay clave")
        self.interprete_remoto = QLineEdit("python3")
        self.carpeta_remota = QLineEdit("~/mova_dgx_trainer/trabajos")
        examinar = QHBoxLayout()
        examinar.addWidget(self.clave, 1)
        examinar.addWidget(boton("Examinar…", al_pulsar=self._elegir_clave))
        rejilla.addWidget(campo("Intérprete local (vacío = el de la app o el del PATH)",
                                self.interprete_local), 0, 0, 1, 2)
        rejilla.addWidget(campo("Host", self.host), 1, 0)
        rejilla.addWidget(campo("Puerto", self.puerto), 1, 1)
        rejilla.addWidget(campo("Usuario", self.usuario), 2, 0)
        rejilla.addWidget(campo("Contraseña", self.contrasena), 2, 1)
        rejilla.addLayout(examinar, 3, 0, 1, 2)
        rejilla.addWidget(campo("Intérprete remoto", self.interprete_remoto), 4, 0)
        rejilla.addWidget(campo("Carpeta de trabajo remota", self.carpeta_remota), 4, 1)
        conexion.anadir(rejilla)
        conexion.anadir(etiqueta("La primera conexión acepta y guarda la huella del host; si "
                                 "después cambia, la conexión se rechaza.", "apoyo"))
        botones = QHBoxLayout()
        self.guardar = boton("Guardar configuración", "principal", self._guardar)
        self.comprobar = boton("Comprobar entorno", al_pulsar=self._comprobar)
        botones.addWidget(self.guardar)
        botones.addWidget(self.comprobar)
        botones.addStretch(1)
        conexion.anadir(botones)
        fila.addWidget(conexion, 3)

        entorno = Tarjeta("Entorno detectado", "nvidia-smi, versión de Python e import de "
                                               "scikit-learn, PyTorch y TensorFlow.")
        self.tabla_entorno = TablaExportable(["Componente", "Disponible", "Versión"],
                                             coord.exportar_tabla, "entorno", alto_minimo=190)
        entorno.anadir(self.tabla_entorno, 1)
        fila.addWidget(entorno, 2)
        self.capa.addLayout(fila)

        self.panel = PanelTrabajo("Registro de comprobaciones", 80)
        self.capa.addWidget(self.panel)

        fila2 = QHBoxLayout()
        fila2.setSpacing(12)
        copias = Tarjeta("Copias de seguridad", "Se crea una al arrancar y se conservan las 10 "
                                                "últimas en almacen/backups/.")
        self.tabla_copias = TablaExportable(["Copia", "Tamaño (KB)"], coord.exportar_tabla,
                                            "copias", alto_minimo=150)
        copias.anadir(self.tabla_copias)
        bc = QHBoxLayout()
        bc.addWidget(boton("Crear copia ahora", al_pulsar=self._copiar))
        bc.addWidget(boton("Restaurar copia seleccionada", "destructivo", self._restaurar))
        bc.addStretch(1)
        copias.anadir(bc)
        fila2.addWidget(copias, 1)

        datos = Tarjeta("Almacén y tablas")
        self.ruta_almacen = etiqueta("", "apoyo")
        datos.anadir(self.ruta_almacen)
        datos.anadir(boton("Abrir carpeta del almacén", al_pulsar=self._abrir_almacen))
        self.tabla_bd = QComboBox()
        self.tabla_bd.addItems(TABLAS)
        exp = QHBoxLayout()
        exp.addWidget(campo("Tabla de la base de datos", self.tabla_bd), 1)
        exp.addWidget(boton("Ver", al_pulsar=self._ver_tabla))
        datos.anadir(exp)
        self.tabla_vista = TablaExportable([""], coord.exportar_tabla, "tabla", alto_minimo=150)
        datos.anadir(self.tabla_vista)
        fila2.addWidget(datos, 1)
        self.capa.addLayout(fila2)

        decisiones = Tarjeta("Decisiones abiertas", "No se cierran desde la aplicación.")
        for d in DECISIONES_ABIERTAS:
            decisiones.anadir(etiqueta_pendiente(d))
        self.capa.addWidget(decisiones)

    # --- carga y guardado ------------------------------------------------------------
    def al_mostrar(self) -> None:
        c = self.coord.cargar_conexion()
        (self.remoto if c.get("modo") == "remoto" else self.local).setChecked(True)
        self.interprete_local.setText(c.get("interprete_local", ""))
        self.host.setText(c.get("host", ""))
        self.puerto.setValue(int(c.get("puerto") or 22))
        self.usuario.setText(c.get("usuario", ""))
        self.clave.setText(c.get("ruta_clave", ""))
        self.contrasena.setText(c.get("contrasena", ""))
        self.interprete_remoto.setText(c.get("interprete_remoto", "python3"))
        self.carpeta_remota.setText(c.get("carpeta_remota", "~/mova_dgx_trainer/trabajos"))
        a = self.coord.almacen
        self.ruta_almacen.setText(f"Almacén: {a.raiz}" + (f"\n{a.nota}" if a.nota else ""))
        self._pintar_copias()

    def _datos(self) -> dict:
        return {"modo": "remoto" if self.remoto.isChecked() else "local",
                "interprete_local": self.interprete_local.text().strip(),
                "host": self.host.text().strip(), "puerto": self.puerto.value(),
                "usuario": self.usuario.text().strip(), "ruta_clave": self.clave.text().strip(),
                "contrasena": self.contrasena.text(),
                "interprete_remoto": self.interprete_remoto.text().strip() or "python3",
                "carpeta_remota": self.carpeta_remota.text().strip()}

    def _guardar(self) -> bool:
        d = self._datos()
        if d["modo"] == "remoto" and not (d["host"] and d["usuario"]):
            self.estado_ui.avisar("Para el modo remoto hacen falta host y usuario.", "warn")
            return False
        if not self.servicio_ok(self.coord.guardar_conexion, d)[0]:
            return False
        self.estado_ui.avisar("Configuración guardada (cifrada).")
        return True

    def _elegir_clave(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Clave privada SSH", str(Path.home() / ".ssh"))
        if ruta:
            self.clave.setText(ruta)

    # --- entorno -----------------------------------------------------------------------
    def _comprobar(self) -> None:
        if not self._guardar():
            return
        self.lanzar(self.coord.comprobar_entorno, panel=self.panel,
                    al_terminar=self._al_comprobar, botones=[self.comprobar, self.guardar])

    def _al_comprobar(self, r: dict) -> None:
        filas = [[f["componente"], "sí" if f["disponible"] else "no",
                  f["version"] if f["version"] else pendiente("no detectado")] for f in r["filas"]]
        niveles = {(i, 2): "pend" for i, f in enumerate(r["filas"]) if not f["version"]}
        self.tabla_entorno.cargar(filas, r["filas"], niveles)
        self.estado_ui.avisar(f"Entorno comprobado en {r['modo']}.")

    # --- copias y tablas -----------------------------------------------------------------
    def _pintar_copias(self) -> None:
        copias = self.coord.listar_copias()
        self.tabla_copias.cargar([[c.name, f"{c.stat().st_size / 1024:.0f}"] for c in copias],
                                 copias)

    def _copiar(self) -> None:
        if self.servicio(self.coord.crear_copia):
            self._pintar_copias()
            self.estado_ui.avisar("Copia creada.")

    def _restaurar(self) -> None:
        copia = self.tabla_copias.dato_seleccionado()
        if not copia:
            self.estado_ui.avisar("Seleccione una copia de la lista.", "warn")
            return
        if not confirmar(self, f"¿Restaurar {copia.name}?",
                         "Se sustituirá la base de datos actual. Antes se guarda una copia de "
                         "seguridad del estado actual."):
            return
        if self.servicio_ok(self.coord.restaurar_copia, copia)[0]:
            self._pintar_copias()
            self.estado_ui.avisar("Copia restaurada.", "warn")
            self.estado_ui.datos_cambiados.emit()

    def _abrir_almacen(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.coord.almacen.raiz)))

    def _ver_tabla(self) -> None:
        resultado = self.servicio(self.coord.tabla, self.tabla_bd.currentText())
        if not resultado:
            return
        cabecera, filas = resultado
        t = self.tabla_vista.tabla
        t.setColumnCount(len(cabecera))
        t.setHorizontalHeaderLabels(cabecera)
        t.cargar([list(f) for f in filas[-500:]])
