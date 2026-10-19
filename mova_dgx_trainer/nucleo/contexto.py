"""Contexto de un trabajo largo: callbacks de progreso, log y cancelación.

No depende de Qt: el núcleo se puede usar y probar sin interfaz. La UI lo
construye desde `infra.hilos.TrabajoBase` y conecta las callbacks a señales.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

PENDIENTE = "[PENDIENTE: {}]"


def pendiente(dato: str) -> str:
    return PENDIENTE.format(dato)


class Cancelado(Exception):
    """El usuario ha cancelado el trabajo."""


@dataclass
class Contexto:
    al_progreso: Callable[[int], None] = lambda _p: None
    al_log: Callable[[str], None] = lambda _t: None
    al_evento: Callable[[dict], None] = lambda _e: None
    _cancelado: threading.Event = field(default_factory=threading.Event)
    _al_cancelar: list = field(default_factory=list)

    def progreso(self, porcentaje: float) -> None:
        self.al_progreso(max(0, min(100, int(porcentaje))))

    def log(self, texto: str) -> None:
        self.al_log(texto)

    def evento(self, evento: dict) -> None:
        self.al_evento(evento)

    def cancelado(self) -> bool:
        return self._cancelado.is_set()

    def comprobar(self) -> None:
        if self._cancelado.is_set():
            raise Cancelado("Trabajo cancelado por el usuario.")

    def registrar_al_cancelar(self, funcion: Callable[[], None]) -> None:
        self._al_cancelar.append(funcion)

    def cancelar(self) -> None:
        self._cancelado.set()
        for f in list(self._al_cancelar):
            try:
                f()
            except Exception:  # noqa: BLE001 - cancelar nunca debe romper
                pass
