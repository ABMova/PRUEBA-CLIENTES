"""Word como motor de PDF (y del índice) de los informes MOVA.

Por qué un hilo propio con Word abierto un rato: en este equipo la PRIMERA exportación a PDF de cada
instancia de Word tarda unos 50 s (Windows consulta la impresora predeterminada, de red) y las
siguientes menos de 1 s. Así que:
  - calentar() abre Word en segundo plano cuando es probable que se vaya a exportar
    (al abrir una consulta terminada), y hace esa primera exportación con un documento vacío;
  - Word se cierra solo tras MINUTOS_LIBRE sin uso, para no dejar un Word invisible abierto;
  - COM exige que todo se haga desde el mismo hilo: las peticiones van por una cola.

preparar(docx, pdf) abre el .docx, actualiza el índice y los campos (números de página reales),
lo guarda y, si se pide, exporta el PDF. Si Word no está instalado devuelve False y el exportador
recurre a LibreOffice.
"""
import atexit
import logging
import os
import queue
import subprocess
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)
MINUTOS_LIBRE = 5
ESPERA_MAXIMA_S = 240  # incluye la primera exportación lenta y un documento largo

_cola: "queue.Queue[tuple]" = queue.Queue()
_hilo: threading.Thread | None = None
_bloqueo = threading.Lock()
_disponible: bool | None = None  # None = sin probar todavía
_caliente = False                # Word abierto y con la primera exportación ya hecha
_calentando = False
_pid_word: int | None = None     # el WINWORD.EXE que abrimos nosotros (Windows lo arranca aparte, no como hijo)
_antes_de_abrir: set[int] | None = None  # los Word que había mientras el nuestro arranca (DispatchEx tarda segundos)


def _pids_word() -> set[int]:
    try:
        salida = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
                                capture_output=True, text=True, timeout=15, encoding="oem", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {int(l.split('","')[1]) for l in salida.splitlines() if l.startswith('"WINWORD.EXE"')}


def cerrar_word() -> None:
    """Mata el Word invisible de la aplicación. Se usa al cerrar el motor: si no, quedaría vivo sin ventana,
    porque Windows lo arranca aparte y no muere con el proceso que lo pidió."""
    global _pid_word
    pids = {_pid_word} if _pid_word else set()
    if not pids and _antes_de_abrir is not None:
        # Cierre a medio arranque: el proceso ya existe pero DispatchEx aún no ha vuelto
        pids = _pids_word() - _antes_de_abrir
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.info("Word de la aplicación cerrado (PID %s).", pid)
    _pid_word = None


atexit.register(cerrar_word)


def _trabajar() -> None:
    import pythoncom
    import win32com.client
    global _disponible, _caliente, _calentando, _pid_word, _antes_de_abrir
    pythoncom.CoInitialize()
    word = None
    try:
        while True:
            try:
                tarea = _cola.get(timeout=MINUTOS_LIBRE * 60 if word else None)
            except queue.Empty:
                log.info("Word sin uso %s min: se cierra.", MINUTOS_LIBRE)
                _cerrar(word)
                word, _caliente = None, False
                continue
            tipo, docx, pdf, hecho, resultado = tarea
            try:
                if word is None:
                    _antes_de_abrir = _pids_word()
                    word = win32com.client.DispatchEx("Word.Application")
                    nuevos = _pids_word() - _antes_de_abrir
                    _pid_word = nuevos.pop() if len(nuevos) == 1 else None
                    _antes_de_abrir = None
                    if _pid_word is None:
                        log.warning("No se identificó el proceso de Word (%s nuevos).", len(nuevos))
                    word.Visible = False
                    word.DisplayAlerts = 0
                    _disponible = True
                if tipo == "calentar":
                    d = word.Documents.Add()
                    d.Content.Text = "."
                    with tempfile.TemporaryDirectory() as t:
                        d.ExportAsFixedFormat(str(Path(t) / "calentar.pdf"), 17)
                    d.Close(False)
                    resultado["ok"] = True
                    log.info("Word preparado para exportar informes.")
                else:
                    d = word.Documents.Open(str(docx), False, False, False)  # ConfirmConversions, ReadOnly, AddToRecent
                    for i in range(1, d.TablesOfContents.Count + 1):
                        d.TablesOfContents(i).Update()
                    d.Fields.Update()
                    d.Save()
                    if pdf:
                        d.ExportAsFixedFormat(str(pdf), 17)  # wdExportFormatPDF
                    d.Close(False)
                    resultado["ok"] = True
                _caliente = True
            except Exception as e:  # sin Word, o Word falla: el exportador probará con LibreOffice
                if word is None:
                    _disponible = False
                    _antes_de_abrir = None
                log.warning("Word no pudo %s: %s", tipo, e)
                resultado["error"] = str(e)
                _cerrar(word)
                word, _caliente = None, False
            finally:
                if tipo == "calentar":
                    _calentando = False
                hecho.set()
    finally:
        _cerrar(word)
        pythoncom.CoUninitialize()


def _cerrar(word) -> None:
    global _pid_word
    if word is not None:
        try:
            word.Quit(False)
            _pid_word = None
        except Exception:
            cerrar_word()


def _encolar(tipo, docx=None, pdf=None, esperar=True) -> bool:
    global _hilo
    if os.name != "nt" or _disponible is False:
        return False
    with _bloqueo:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_trabajar, name="word-pdf", daemon=True)
            _hilo.start()
    hecho, resultado = threading.Event(), {}
    _cola.put((tipo, docx, pdf, hecho, resultado))
    if not esperar:
        return True
    if not hecho.wait(ESPERA_MAXIMA_S):
        log.warning("Word no terminó en %s s", ESPERA_MAXIMA_S)
        return False
    return bool(resultado.get("ok"))


def calentar() -> None:
    """Abre Word y hace la primera exportación (la lenta) sin que nadie espere."""
    global _calentando
    if not _caliente and not _calentando and _disponible is not False:
        _calentando = True
        _encolar("calentar", esperar=False)


def preparar(docx: Path, pdf: Path | None = None) -> bool:
    """Actualiza índice y campos del .docx con Word y, si se pide, exporta el PDF. False si no hay Word."""
    return _encolar("preparar", Path(docx).resolve(), Path(pdf).resolve() if pdf else None)
