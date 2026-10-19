"""Hilos de trabajo: ningún proceso largo corre en el hilo de la interfaz."""
from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from nucleo.contexto import Cancelado, Contexto

log = logging.getLogger(__name__)


class TrabajoBase(QThread):
    """QThread con señales progreso/log/terminado/error y cancelación cooperativa.

    Las subclases implementan `ejecutar(ctx) -> dict`. `cancelar()` marca el
    contexto y ejecuta las funciones registradas (p. ej. terminar el subproceso).
    """

    progreso = Signal(int)
    log = Signal(str)
    evento = Signal(dict)
    terminado = Signal(dict)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ctx = Contexto(al_progreso=self.progreso.emit,
                            al_log=self.log.emit,
                            al_evento=self.evento.emit)

    def ejecutar(self, ctx: Contexto) -> dict:  # pragma: no cover - abstracto
        raise NotImplementedError

    def cancelar(self) -> None:
        self.ctx.log("Cancelación solicitada.")
        self.ctx.cancelar()

    def run(self) -> None:  # noqa: D401 - API de Qt
        try:
            resultado = self.ejecutar(self.ctx) or {}
            self.terminado.emit(resultado)
        except Cancelado as e:
            self.error.emit(f"CANCELADO|{e}")
        except Exception as e:  # noqa: BLE001
            log.error("Error en %s:\n%s", type(self).__name__, traceback.format_exc())
            self.log.emit(traceback.format_exc())
            self.error.emit(str(e) or type(e).__name__)


class TrabajoFuncion(TrabajoBase):
    """Ejecuta `funcion(ctx, *args, **kwargs)` en un hilo."""

    def __init__(self, funcion: Callable[..., Any], *args, parent=None, **kwargs):
        super().__init__(parent)
        self._funcion = funcion
        self._args = args
        self._kwargs = kwargs

    def ejecutar(self, ctx: Contexto) -> dict:
        resultado = self._funcion(ctx, *self._args, **self._kwargs)
        if isinstance(resultado, dict):
            return resultado
        return {"resultado": resultado}
