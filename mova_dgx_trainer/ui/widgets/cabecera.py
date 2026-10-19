"""Cabecera a todo el ancho: degradado 120°, halo dorado girado −12° y logotipos."""
from __future__ import annotations

import base64
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from ui.estilos.paleta import PALETA

ANCHO_LOGO, ANCHO_LOGO_ESTRECHO, UMBRAL_ESTRECHO = 120, 78, 820
LADO_CEREBRO = 60


def pixmap_base64(datos: str) -> QPixmap | None:
    if not datos:
        return None
    pm = QPixmap()
    if not pm.loadFromData(base64.b64decode(datos), "PNG"):
        return None
    return pm


def _imagenes() -> tuple[str, str]:
    try:
        from ui.recursos import imagenes_base64 as img
        return img.CEREBRO_PNG, img.LOGO_MOVA_PNG
    except ImportError:
        return "", ""


class Cabecera(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cabecera")
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFixedHeight(92)
        cerebro_b64, logo_b64 = _imagenes()
        self._logo = pixmap_base64(logo_b64)

        capa = QHBoxLayout(self)
        capa.setContentsMargins(24, 14, 24, 14)
        capa.setSpacing(14)

        self.cerebro = QLabel()
        self.cerebro.setFixedSize(LADO_CEREBRO, LADO_CEREBRO)
        cerebro = pixmap_base64(cerebro_b64)
        if cerebro:
            self.cerebro.setPixmap(cerebro.scaled(LADO_CEREBRO, LADO_CEREBRO, Qt.KeepAspectRatio,
                                                  Qt.SmoothTransformation))
        sombra = QGraphicsDropShadowEffect(self.cerebro)
        sombra.setBlurRadius(22)
        sombra.setOffset(0, 0)
        sombra.setColor(QColor(217, 180, 91, 80))
        self.cerebro.setGraphicsEffect(sombra)
        capa.addWidget(self.cerebro)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel("MOVA DGX Spark Trainer")
        titulo.setObjectName("tituloApp")
        subtitulo = QLabel("Entrenamiento local de modelos sobre DGX Spark")
        subtitulo.setObjectName("subtituloApp")
        textos.addStretch(1)
        textos.addWidget(titulo)
        textos.addWidget(subtitulo)
        textos.addStretch(1)
        capa.addLayout(textos)
        capa.addStretch(1)

        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        capa.addWidget(self.logo)
        self._ancho_logo = 0
        self._ajustar_logo(ANCHO_LOGO)

    def _ajustar_logo(self, ancho: int) -> None:
        if ancho == self._ancho_logo:
            return
        self._ancho_logo = ancho
        if self._logo:
            self.logo.setPixmap(self._logo.scaledToWidth(ancho, Qt.SmoothTransformation))
        else:
            # Logotipo en texto: «MOVA» en blanco e «IA» en dorado al 40 %, trazo fino.
            alto = max(12, int(ancho / 4.2))
            self.logo.setText(
                f'<span style="color:#ffffff; font-size:{alto}px; font-weight:300; '
                f'letter-spacing:3px;">MOVA</span>'
                f'<span style="color:{PALETA["gold"]}; font-size:{int(alto * 0.4)}px; '
                f'font-weight:300; letter-spacing:2px;"> IA</span>')

    def resizeEvent(self, evento) -> None:  # noqa: N802 - API de Qt
        ventana = self.window()
        ancho = ventana.width() if ventana else self.width()
        self._ajustar_logo(ANCHO_LOGO_ESTRECHO if ancho < UMBRAL_ESTRECHO else ANCHO_LOGO)
        super().resizeEvent(evento)

    def paintEvent(self, evento) -> None:  # noqa: N802 - API de Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Degradado lineal 120° (convención CSS): #0b0c0e 0% → #141518 58% → #1c1710 100%
        ang = math.radians(120)
        dx, dy = math.sin(ang), -math.cos(ang)
        largo = abs(w * dx) + abs(h * dy)
        cx, cy = w / 2, h / 2
        grad = QLinearGradient(QPointF(cx - dx * largo / 2, cy - dy * largo / 2),
                               QPointF(cx + dx * largo / 2, cy + dy * largo / 2))
        grad.setColorAt(0.0, QColor("#0b0c0e"))
        grad.setColorAt(0.58, QColor("#141518"))
        grad.setColorAt(1.0, QColor("#1c1710"))
        p.fillRect(self.rect(), grad)

        # Halo dorado arriba a la derecha, elíptico y girado −12°
        radio = max(h * 1.9, 220.0)
        p.save()
        p.translate(w - radio * 0.55, h * 0.05)
        p.rotate(-12)
        p.scale(1.7, 1.0)
        halo = QRadialGradient(QPointF(0, 0), radio)
        halo.setColorAt(0.0, QColor(217, 180, 91, int(0.30 * 255)))
        halo.setColorAt(0.60, QColor(217, 180, 91, int(0.07 * 255)))
        halo.setColorAt(0.76, QColor(217, 180, 91, 0))
        halo.setColorAt(1.0, QColor(217, 180, 91, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(-radio, -radio, 2 * radio, 2 * radio))
        p.restore()

        # Borde inferior de 1 px en --border
        p.setPen(QPen(QColor(PALETA["border"]), 1))
        p.drawLine(0, h - 1, w, h - 1)
        p.end()


