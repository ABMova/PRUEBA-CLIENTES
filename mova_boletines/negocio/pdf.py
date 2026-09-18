"""HTML -> PDF con el navegador del equipo (Edge o Chrome sin ventana).

Es el mismo motor que el boton "Imprimir" del documento, asi que el PDF sale
igual que la hoja impresa: pie al final de cada pagina, logo y edificio de
fondo. No hace falta instalar nada en Windows (Edge viene con el sistema).
En Linux (VPS) hay que instalar Chromium: `apt install chromium`.

Seguridad: el navegador arranca con un perfil vacio y temporal, sin
extensiones y sin red (las imagenes ya van dentro del HTML en base64), y se
cierra al terminar.

Para usar otro navegador: variable MOVA_NAVEGADOR_PDF con la ruta del .exe.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

registro = logging.getLogger("mova")

ESPERA_MAXIMA_S = 90
# Varios PDF a la vez = varios navegadores abiertos; con dos basta.
_turnos = threading.BoundedSemaphore(2)


class ErrorPdf(Exception):
    pass


def _candidatos() -> list[str]:
    propio = os.getenv("MOVA_NAVEGADOR_PDF", "").strip()
    if propio:
        return [propio]
    if sys.platform == "win32":
        bases = [os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.getenv("ProgramFiles", r"C:\Program Files"),
                 os.getenv("LOCALAPPDATA", "")]
        relativas = [r"Microsoft\Edge\Application\msedge.exe",
                     r"Google\Chrome\Application\chrome.exe"]
        return [str(Path(b) / r) for r in relativas for b in bases if b]
    nombres = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
               "microsoft-edge", "microsoft-edge-stable"]
    return [ruta for ruta in (shutil.which(n) for n in nombres) if ruta]


def navegador() -> str | None:
    """Ruta del navegador que se usara, o None si no hay ninguno."""
    return next((c for c in _candidatos() if Path(c).is_file()), None)


def html_a_pdf(html: str) -> bytes:
    programa = navegador()
    if not programa:
        raise ErrorPdf("No se encuentra Edge ni Chrome para crear el PDF")
    if not _turnos.acquire(timeout=ESPERA_MAXIMA_S):
        raise ErrorPdf("Hay demasiados PDF generandose a la vez")
    try:
        # Edge puede tardar un instante en soltar el perfil: no fallar al limpiarlo.
        with tempfile.TemporaryDirectory(prefix="mova-pdf-", ignore_cleanup_errors=True) as carpeta:
            carpeta_ruta = Path(carpeta)
            entrada = carpeta_ruta / "documento.html"
            salida = carpeta_ruta / "documento.pdf"
            entrada.write_text(html, encoding="utf-8")
            orden = [
                programa,
                "--headless=new",
                "--disable-gpu",
                "--window-size=1000,1400",  # la infografia se maqueta a su ancho completo
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                "--host-resolver-rules=MAP * ~NOTFOUND",
                f"--user-data-dir={carpeta_ruta / 'perfil'}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={salida}",
                entrada.as_uri(),
            ]
            if sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() == 0:
                orden.insert(1, "--no-sandbox")  # Chromium no arranca como root sin esto
            extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            try:
                subprocess.run(orden, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=ESPERA_MAXIMA_S, check=False,
                               **extra)
            except subprocess.TimeoutExpired as exc:
                raise ErrorPdf("El navegador tardo demasiado en crear el PDF") from exc
            if not salida.is_file() or salida.stat().st_size == 0:
                raise ErrorPdf("El navegador no genero el PDF")
            datos = salida.read_bytes()
            if not datos.startswith(b"%PDF"):
                raise ErrorPdf("El fichero generado no es un PDF")
            return datos
    finally:
        _turnos.release()
