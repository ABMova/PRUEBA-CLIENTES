"""MOVA DGX Spark Trainer · punto de entrada.

    python main.py                       abre la aplicación
    python main.py --prueba-arranque     abre, recorre todas las pantallas, comprueba el QSS
                                         y los avisos de Qt, y se cierra (código 0 si todo bien)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from PySide6.QtCore import QtMsgType, QTimer, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QColor, QFont, QIcon, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from infra import registro  # noqa: E402
from infra.cifrado import Cifrador  # noqa: E402
from infra.rutas import resolver_almacen, ruta_recurso  # noqa: E402

log = logging.getLogger("arranque")
AVISOS_QT: list[str] = []


def _manejador_qt(tipo, contexto, mensaje) -> None:
    if tipo in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        AVISOS_QT.append(mensaje)
        log.warning("Qt: %s", mensaje)
    else:
        log.debug("Qt: %s", mensaje)


def cargar_qss() -> str:
    ruta = ruta_recurso("ui", "estilos", "mova.qss")
    if ruta.exists():
        return ruta.read_text(encoding="utf-8")
    from ui.estilos.paleta import generar_qss  # respaldo: generarlo desde la paleta
    log.warning("No se encontró %s; se genera desde la paleta.", ruta)
    return generar_qss()


def paleta_qt() -> QPalette:
    from ui.estilos.paleta import PALETA
    p = QPalette()
    for rol, clave in ((QPalette.Window, "bg"), (QPalette.Base, "field"),
                       (QPalette.AlternateBase, "card"), (QPalette.Button, "card"),
                       (QPalette.WindowText, "text"), (QPalette.Text, "text"),
                       (QPalette.ButtonText, "text"), (QPalette.Highlight, "gold-d"),
                       (QPalette.HighlightedText, "gold-txt"), (QPalette.ToolTipBase, "card-2"),
                       (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted")):
        p.setColor(rol, QColor(PALETA[clave]))
    return p


def prueba_arranque(app: QApplication, ventana) -> int:
    """Recorre las pantallas y comprueba QSS y avisos de Qt."""
    errores = []
    qss = app.styleSheet()
    if not qss or "#0b0c0e" not in qss or "QFrame#tarjeta" not in qss:
        errores.append("El QSS no se ha cargado.")
    for clave in list(ventana.pantallas):
        ventana.ir_a(clave)
        app.processEvents()
    ventana.ir_a("proyecto")
    app.processEvents()
    if AVISOS_QT:
        errores.append(f"{len(AVISOS_QT)} aviso(s) de Qt: " + " | ".join(AVISOS_QT[:5]))
    print(f"QSS cargado: {len(qss)} caracteres")
    print(f"Pantallas recorridas: {', '.join(ventana.pantallas)}")
    print(f"Avisos de Qt: {len(AVISOS_QT)}")
    print(f"Almacén: {ventana.coord.almacen.raiz}")
    for e in errores:
        print(f"ERROR: {e}")
    print("PRUEBA DE ARRANQUE: " + ("OK" if not errores else "FALLO"))
    return 0 if not errores else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MOVA DGX Spark Trainer")
    parser.add_argument("--prueba-arranque", action="store_true",
                        help="abre, comprueba y cierra (para pruebas automáticas)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # La plataforma offscreen no lee las fuentes del sistema: se le indica dónde están.
    fuentes_windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if (os.environ.get("QT_QPA_PLATFORM") == "offscreen" and "QT_QPA_FONTDIR" not in os.environ
            and fuentes_windows.is_dir()):
        os.environ["QT_QPA_FONTDIR"] = str(fuentes_windows)

    almacen = resolver_almacen()
    registro.configurar(almacen.logs)
    log.info("Arranque. Almacén en %s", almacen.raiz)
    if almacen.nota:
        log.warning(almacen.nota)
    qInstallMessageHandler(_manejador_qt)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("MOVA DGX Spark Trainer")
    app.setOrganizationName("MOVA")
    app.setStyle("Fusion")
    app.setPalette(paleta_qt())
    fuente = QFont("Segoe UI")
    fuente.setPixelSize(12)
    app.setFont(fuente)
    icono = ruta_recurso("ui", "recursos", "icono.ico")
    if icono.exists():
        app.setWindowIcon(QIcon(str(icono)))
    app.setStyleSheet(cargar_qss())

    from nucleo.coordinador import Coordinador
    from ui.ventana_principal import VentanaPrincipal

    coord = Coordinador(almacen, Cifrador(almacen.config))
    info = coord.al_arrancar()
    log.info("Copia de arranque: %s · ejecuciones interrumpidas: %s · migración %s",
             info["copia"], info["interrumpidas"], info["migracion"])

    def excepcion_no_capturada(tipo, valor, tb):
        log.error("Excepción no capturada:\n%s", "".join(traceback.format_exception(tipo, valor, tb)))
        if args.prueba_arranque:
            AVISOS_QT.append(f"Excepción: {valor}")
            return
        QMessageBox.critical(None, "MOVA DGX Spark Trainer",
                             f"Se ha producido un error inesperado ({valor}).\n"
                             "Revise almacen/logs/aplicacion.log y vuelva a intentarlo.")

    sys.excepthook = excepcion_no_capturada

    ventana = VentanaPrincipal(coord)
    if almacen.nota:
        ventana.avisar(almacen.nota, "warn")
    ventana.show()

    resultado = {"codigo": 1}
    if args.prueba_arranque:
        def comprobar():
            resultado["codigo"] = prueba_arranque(app, ventana)
            ventana.close()
            app.quit()

        QTimer.singleShot(800, comprobar)
        app.exec()
    else:
        resultado["codigo"] = app.exec()

    # Cierre ordenado: sin esto, Python puede destruir la QApplication antes que
    # los widgets y Qt falla al salir (access violation intermitente en Windows).
    qInstallMessageHandler(None)
    sys.excepthook = sys.__excepthook__
    ventana.deleteLater()
    del ventana
    app.processEvents()
    app.shutdown()
    log.info("Cierre de la aplicación.")
    return resultado["codigo"]


if __name__ == "__main__":
    sys.exit(main())
