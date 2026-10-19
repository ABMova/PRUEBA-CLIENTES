"""Base de las pantallas: estado compartido, panel de trabajo y lanzamiento en hilos."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from infra.hilos import TrabajoFuncion
from nucleo.coordinador import Coordinador, ErrorServicio
from ui.widgets.barra_progreso import BarraProgreso
from ui.widgets.comun import boton, mostrar_error, mostrar_error_trabajo
from ui.widgets.registro_vivo import RegistroVivo
from ui.widgets.tarjeta import Tarjeta


class EstadoUI(QObject):
    """Estado compartido entre pantallas (proyecto activo y avisos)."""

    proyecto_cambiado = Signal(int)
    ir_a = Signal(str)
    aviso = Signal(str, str)
    datos_cambiados = Signal()

    def __init__(self):
        super().__init__()
        self.proyecto_id: int | None = None

    def abrir(self, proyecto_id: int) -> None:
        self.proyecto_id = proyecto_id
        self.proyecto_cambiado.emit(proyecto_id)

    def avisar(self, texto: str, gravedad: str = "ok") -> None:
        self.aviso.emit(texto, gravedad)


class PanelTrabajo(Tarjeta):
    """Barra de 10 px, registro en vivo con hora y botón Cancelar."""

    def __init__(self, titulo: str = "Progreso", alto_registro: int = 150):
        super().__init__(titulo)
        fila = QHBoxLayout()
        self.barra = BarraProgreso()
        self.estado = QLabel("En espera.")
        self.estado.setProperty("rol", "apoyo")
        self.cancelar = boton("Cancelar")
        self.cancelar.setEnabled(False)
        fila.addWidget(self.barra, 1)
        fila.addWidget(self.cancelar)
        self.anadir(fila)
        self.anadir(self.estado)
        self.registro = RegistroVivo(alto_minimo=alto_registro)
        self.anadir(self.registro, 1)


class PasoBase(QWidget):
    titulo = ""

    def __init__(self, coord: Coordinador, estado: EstadoUI, parent=None):
        super().__init__(parent)
        self.coord, self.estado_ui = coord, estado
        self.trabajo: TrabajoFuncion | None = None
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(0, 0, 0, 0)
        self.capa.setSpacing(12)

    # --- utilidades ---------------------------------------------------------
    @property
    def pid(self) -> int | None:
        return self.estado_ui.proyecto_id

    def al_mostrar(self) -> None:
        """Se llama cada vez que la pantalla pasa a primer plano."""

    def ocupado(self) -> bool:
        return self.trabajo is not None and self.trabajo.isRunning()

    def servicio(self, funcion: Callable, *args, **kwargs):
        """Llama a un servicio rápido; los errores se muestran en un QMessageBox accionable.

        Devuelve el resultado, o None si ha fallado.
        """
        ok, resultado = self.servicio_ok(funcion, *args, **kwargs)
        return resultado if ok else None

    def servicio_ok(self, funcion: Callable, *args, **kwargs) -> tuple[bool, object]:
        try:
            return True, funcion(*args, **kwargs)
        except ErrorServicio as e:
            mostrar_error(self, e.que_paso, e.que_hacer)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("Error en servicio")
            mostrar_error(self, f"Error inesperado: {e}",
                          "Revise el registro de la aplicación y vuelva a intentarlo")
        return False, None

    def lanzar(self, funcion: Callable, *args, panel: PanelTrabajo,
               al_terminar: Callable[[dict], None], botones: list | None = None,
               al_evento: Callable[[dict], None] | None = None, **kwargs) -> None:
        """Ejecuta `funcion(ctx, *args)` en un QThread; la ventana nunca se congela."""
        if self.ocupado():
            self.estado_ui.avisar("Ya hay un trabajo en curso en esta pantalla.", "warn")
            return
        botones = botones or []
        trabajo = TrabajoFuncion(funcion, *args, parent=self, **kwargs)
        self.trabajo = trabajo
        panel.barra.reiniciar()
        panel.estado.setText("En curso…")
        panel.cancelar.setEnabled(True)
        for b in botones:
            b.setEnabled(False)

        def fin():
            panel.cancelar.setEnabled(False)
            for b in botones:
                b.setEnabled(True)

        def ok(resultado: dict):
            fin()
            panel.barra.setValue(100)
            panel.estado.setText("Terminado.")
            al_terminar(resultado)

        def error(mensaje: str):
            fin()
            if mostrar_error_trabajo(self, mensaje):
                panel.estado.setText("Terminado con error.")
                self.estado_ui.avisar(mensaje.split("|")[0], "err")
            else:
                panel.estado.setText("Cancelado.")
                self.estado_ui.avisar("Trabajo cancelado.", "warn")

        trabajo.progreso.connect(panel.barra.setValue)
        trabajo.log.connect(panel.registro.anadir)
        if al_evento:
            trabajo.evento.connect(al_evento)
        trabajo.terminado.connect(ok)
        trabajo.error.connect(error)
        trabajo.finished.connect(lambda: setattr(self, "trabajo", None)
                                 if self.trabajo is trabajo else None)
        try:
            panel.cancelar.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        panel.cancelar.clicked.connect(trabajo.cancelar)
        trabajo.start()

    def esperar_trabajo(self, ms: int = 10000) -> None:
        if self.trabajo is not None:
            self.trabajo.cancelar()
            self.trabajo.wait(ms)
