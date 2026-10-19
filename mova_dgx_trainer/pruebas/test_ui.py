"""La interfaz con un proyecto completo: todas las pantallas sin excepciones ni avisos de Qt."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FUENTES = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
if FUENTES.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(FUENTES))

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

AVISOS: list[str] = []


def _manejador(tipo, _ctx, mensaje):
    if tipo in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        AVISOS.append(mensaje)


@pytest.fixture(scope="module")
def app():
    qInstallMessageHandler(_manejador)
    import main
    aplicacion = QApplication.instance() or QApplication([])
    aplicacion.setStyleSheet(main.cargar_qss())
    yield aplicacion
    qInstallMessageHandler(None)


def test_qss_generado_coincide_con_paleta():
    from ui.estilos.paleta import generar_qss, ruta_qss
    assert ruta_qss().read_text(encoding="utf-8") == generar_qss(), \
        "mova.qss no está al día: ejecute python -m ui.estilos.paleta"
    for valor in ("#0b0c0e", "#d9b45b", "#f0d98c", "#b8892f", "#1a1405", "#2a2d33"):
        assert valor in generar_qss()


def test_pantallas_con_proyecto(app, tmp_path):
    from pruebas.humo_end2end import ejecutar
    from infra.cifrado import Cifrador
    from infra.rutas import Almacen
    from nucleo.coordinador import Coordinador
    from ui.ventana_principal import VentanaPrincipal

    ejecutar(tmp_path, verbose=False)
    almacen = Almacen(tmp_path / "almacen")
    coord = Coordinador(almacen, Cifrador(almacen.config))
    ventana = VentanaPrincipal(coord)
    ventana.show()
    pid = coord.listar_proyectos()[0]["id"]
    ventana.estado.abrir(pid)
    for clave in ventana.pantallas:
        ventana.ir_a(clave)
        app.processEvents()
        assert ventana.pila.currentIndex() == list(ventana.pantallas).index(clave)
    res = ventana.pantallas["resultados"]
    assert res.kpis.kpis["Reintentos"].valor.text() == "0"
    assert res.veredicto.text() in ("aprobado", "insuficiente")
    ventana.resize(800, 600)
    app.processEvents()
    assert ventana.cabecera._ancho_logo == 78
    ventana.close()
    assert not AVISOS, AVISOS
