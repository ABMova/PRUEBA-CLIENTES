"""Piezas comunes de la interfaz: campos con etiqueta, botones y diálogos de error."""
from __future__ import annotations

from PySide6.QtWidgets import (QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from nucleo.contexto import pendiente


def refrescar_estilo(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def boton(texto: str, tipo: str = "normal", al_pulsar=None) -> QPushButton:
    """tipo: principal (UNO por pantalla) | normal | destructivo."""
    b = QPushButton(texto)
    if tipo != "normal":
        b.setProperty("tipo", tipo)
    if al_pulsar:
        b.clicked.connect(al_pulsar)
    return b


def etiqueta(texto: str, rol: str = "etiqueta") -> QLabel:
    e = QLabel(texto)
    e.setProperty("rol", rol)
    e.setWordWrap(True)
    return e


def etiqueta_pendiente(dato: str) -> QLabel:
    e = QLabel(pendiente(dato))
    e.setProperty("pendiente", "true")
    e.setWordWrap(True)
    return e


def marcar_pendiente(lbl: QLabel, texto: str | None, dato: str) -> None:
    """Pone el texto o, si falta, [PENDIENTE: dato] en ámbar."""
    vacio = texto is None or texto == ""
    lbl.setText(pendiente(dato) if vacio else str(texto))
    lbl.setProperty("pendiente", "true" if vacio else "false")
    refrescar_estilo(lbl)


def campo(texto_etiqueta: str, widget: QWidget, ayuda: str = "") -> QWidget:
    """Etiqueta encima en --muted a 0.8rem, el campo y un texto de apoyo opcional."""
    contenedor = QWidget()
    capa = QVBoxLayout(contenedor)
    capa.setContentsMargins(0, 0, 0, 0)
    capa.setSpacing(3)
    capa.addWidget(etiqueta(texto_etiqueta))
    capa.addWidget(widget)
    if ayuda:
        capa.addWidget(etiqueta(ayuda, "apoyo"))
    return contenedor


TEXTO_GENERICO = "Revise el registro de la aplicación y vuelva a intentarlo."


def mostrar_error(padre: QWidget | None, que_paso: str, que_hacer: str = TEXTO_GENERICO) -> None:
    """Dos frases: qué ha pasado y qué hacer. El traceback va al log."""
    caja = QMessageBox(padre)
    caja.setIcon(QMessageBox.Warning)
    caja.setWindowTitle("MOVA DGX Spark Trainer")
    caja.setText(f"{que_paso.rstrip('.')}.\n{que_hacer.rstrip('.')}.")
    caja.exec()


def mostrar_error_trabajo(padre: QWidget | None, mensaje: str) -> bool:
    """Interpreta el mensaje de error de un hilo ('que_paso|que_hacer').

    Devuelve False si era una cancelación (no se muestra diálogo).
    """
    if mensaje.startswith("CANCELADO|"):
        return False
    que_paso, _, que_hacer = mensaje.partition("|")
    mostrar_error(padre, que_paso or "Se ha producido un error", que_hacer or TEXTO_GENERICO)
    return True


def confirmar(padre: QWidget | None, pregunta: str, detalle: str = "") -> bool:
    caja = QMessageBox(padre)
    caja.setIcon(QMessageBox.Question)
    caja.setWindowTitle("MOVA DGX Spark Trainer")
    caja.setText(pregunta)
    if detalle:
        caja.setInformativeText(detalle)
    caja.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    caja.setDefaultButton(QMessageBox.No)
    return caja.exec() == QMessageBox.Yes
