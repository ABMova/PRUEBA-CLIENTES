"""Ventana principal: cabecera, navegación fija por pasos y columna de 1280 px."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from nucleo.coordinador import Coordinador
from ui.panel_configuracion import PanelConfiguracion
from ui.paso_base import EstadoUI, PasoBase
from ui.paso_dataset import PasoDataset
from ui.paso_entrenamiento import PasoEntrenamiento
from ui.paso_importacion import PasoImportacion
from ui.paso_informe import PasoInforme
from ui.paso_proyecto import PasoProyecto
from ui.paso_resultados import PasoResultados
from ui.widgets.aviso_flotante import AvisoFlotante
from ui.widgets.cabecera import Cabecera

ANCHO_MAXIMO = 1280
PANTALLAS = [
    ("proyecto", "1", "Proyecto", PasoProyecto),
    ("importacion", "2", "Importación", PasoImportacion),
    ("dataset", "3", "Dataset", PasoDataset),
    ("entrenamiento", "4", "Entrenamiento", PasoEntrenamiento),
    ("resultados", "5", "Resultados", PasoResultados),
    ("informe", "6", "Informe", PasoInforme),
]


def pixmap_candado(lado: int = 11, color: str = "#9aa0a6") -> QPixmap:
    """Candado dibujado (sin emojis ni fuentes de iconos)."""
    pm = QPixmap(lado * 2, lado * 2)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(2.0)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), 1.3))
    arco = QPainterPath()
    arco.addRoundedRect(QRectF(lado * 0.28, lado * 0.08, lado * 0.44, lado * 0.62), 2.5, 2.5)
    p.drawPath(arco)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(lado * 0.12, lado * 0.44, lado * 0.76, lado * 0.5), 1.5, 1.5)
    p.end()
    return pm


class BotonPaso(QPushButton):
    """Botón de paso con el número en un cuadradito."""

    def __init__(self, numero: str, texto: str):
        super().__init__()
        self.setProperty("rol", "paso")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(8, 4, 10, 4)
        capa.setSpacing(7)
        self.numero = QLabel(numero)
        self.numero.setObjectName("numeroPaso")
        self._candado = numero == "candado"
        if self._candado:
            self.numero.setText("")
            self.numero.setPixmap(pixmap_candado())
        self.texto = QLabel(texto)
        self.texto.setObjectName("textoPaso")
        for e in (self.numero, self.texto):
            e.setAttribute(Qt.WA_TransparentForMouseEvents)
            capa.addWidget(e)
        self.setMinimumHeight(32)
        self.setMinimumWidth(self.texto.sizeHint().width() + 46)
        self.toggled.connect(self._al_cambiar)

    def _al_cambiar(self, activo: bool) -> None:
        if self._candado:
            self.numero.setPixmap(pixmap_candado(color="#1a1405" if activo else "#9aa0a6"))
        self.numero.setProperty("activo", "true" if activo else "false")
        self.numero.style().unpolish(self.numero)
        self.numero.style().polish(self.numero)


class VentanaPrincipal(QMainWindow):
    def __init__(self, coord: Coordinador):
        super().__init__()
        self.coord = coord
        self.estado = EstadoUI()
        self.setWindowTitle("MOVA DGX Spark Trainer")
        self.resize(1360, 900)
        self.setMinimumSize(720, 560)

        raiz = QWidget()
        raiz.setObjectName("raiz")
        capa = QVBoxLayout(raiz)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        self.cabecera = Cabecera()
        capa.addWidget(self.cabecera)

        # Navegación fija (fuera de la zona con desplazamiento), centrada a 1280 px
        nav_fila = QHBoxLayout()
        nav_fila.setContentsMargins(16, 12, 16, 8)
        nav_col = QWidget()
        nav_col.setMaximumWidth(ANCHO_MAXIMO)
        nav = QHBoxLayout(nav_col)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(6)
        self.botones: dict[str, BotonPaso] = {}
        for clave, numero, texto, _ in PANTALLAS:
            b = BotonPaso(numero, texto)
            b.clicked.connect(lambda _c=False, k=clave: self.ir_a(k))
            nav.addWidget(b)
            self.botones[clave] = b
        nav.addStretch(1)
        separador = QFrame()
        separador.setObjectName("separadorVertical")
        separador.setFixedHeight(26)
        nav.addWidget(separador)
        b = BotonPaso("candado", "Configuración")
        b.clicked.connect(lambda _c=False: self.ir_a("configuracion"))
        nav.addWidget(b)
        self.botones["configuracion"] = b
        self.proyecto_lbl = QLabel("Sin proyecto abierto")
        self.proyecto_lbl.setProperty("rol", "apoyo")
        nav_fila.addStretch(1)
        nav_fila.addWidget(nav_col, 100)
        nav_fila.addStretch(1)
        capa.addLayout(nav_fila)
        info_fila = QHBoxLayout()
        info_fila.setContentsMargins(16, 0, 16, 6)
        info_col = QWidget()
        info_col.setMaximumWidth(ANCHO_MAXIMO)
        QHBoxLayout(info_col).addWidget(self.proyecto_lbl)
        info_col.layout().setContentsMargins(0, 0, 0, 0)
        info_fila.addStretch(1)
        info_fila.addWidget(info_col, 100)
        info_fila.addStretch(1)
        capa.addLayout(info_fila)

        self.pila = QStackedWidget()
        self.pantallas: dict[str, PasoBase] = {}
        for clave, _, _, clase in PANTALLAS + [("configuracion", "", "", PanelConfiguracion)]:
            pantalla = clase(coord, self.estado)
            self.pantallas[clave] = pantalla
            self.pila.addWidget(self._envolver(pantalla))
        capa.addWidget(self.pila, 1)
        self.setCentralWidget(raiz)

        self.aviso = AvisoFlotante(raiz)
        self.estado.aviso.connect(self.avisar)
        self.estado.ir_a.connect(self.ir_a)
        self.estado.proyecto_cambiado.connect(self._al_cambiar_proyecto)
        self.estado.datos_cambiados.connect(self._al_cambiar_datos)
        self._actual = ""
        self._actualizar_navegacion()
        self.ir_a("proyecto")

    @staticmethod
    def _envolver(pantalla: QWidget) -> QScrollArea:
        lienzo = QWidget()
        lienzo.setObjectName("lienzo")
        fila = QHBoxLayout(lienzo)
        fila.setContentsMargins(16, 4, 16, 20)
        columna = QWidget()
        columna.setMaximumWidth(ANCHO_MAXIMO)
        QVBoxLayout(columna).addWidget(pantalla)
        columna.layout().setContentsMargins(0, 0, 0, 0)
        fila.addStretch(1)
        fila.addWidget(columna, 100)
        fila.addStretch(1)
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setFrameShape(QFrame.NoFrame)
        zona.setWidget(lienzo)
        return zona

    # --- navegación ---------------------------------------------------------------------
    def ir_a(self, clave: str) -> None:
        if clave not in self.pantallas:
            return
        if clave not in ("proyecto", "configuracion") and not self.estado.proyecto_id:
            self.avisar("Abra o cree un proyecto primero.", "warn")
            clave = "proyecto"
        self._actual = clave
        for k, b in self.botones.items():
            b.setChecked(k == clave)
        indice = list(self.pantallas).index(clave)
        self.pila.setCurrentIndex(indice)
        if self.estado.proyecto_id and clave in dict((c, 1) for c, *_ in PANTALLAS):
            self.coord.ir_a_paso(self.estado.proyecto_id, clave)
        self.pantallas[clave].al_mostrar()

    def _al_cambiar_proyecto(self, pid: int) -> None:
        p = self.coord.proyecto(pid)
        self.proyecto_lbl.setText(f"Proyecto: {p['nombre']} · {p['tipo_tarea']}")
        self._actualizar_navegacion()

    def _al_cambiar_datos(self) -> None:
        self._actualizar_navegacion()
        if self._actual in self.pantallas:
            self.pantallas[self._actual].al_mostrar()

    def _actualizar_navegacion(self) -> None:
        hay = self.estado.proyecto_id is not None
        for clave, *_ in PANTALLAS[1:]:
            self.botones[clave].setEnabled(hay)

    def avisar(self, texto: str, gravedad: str = "ok") -> None:
        self.aviso.mostrar(texto, gravedad)

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self.aviso.recolocar()

    def closeEvent(self, evento) -> None:  # noqa: N802
        for p in self.pantallas.values():
            p.esperar_trabajo(8000)
        super().closeEvent(evento)
