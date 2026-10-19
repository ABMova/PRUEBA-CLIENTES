"""Ejecución de comandos en local (subprocess) o en la DGX Spark por SSH (paramiko).

Ambos ejecutores tienen la misma interfaz:

    ejecutar(comando, cwd, al_recibir_linea, cancelado) -> código de salida
    preparar_carpeta(local, nombre) -> carpeta de trabajo (remota o local)
    recuperar(carpeta_trabajo, destino_local)

En remoto se suben configuración, dataset y script por SFTP y al terminar se
bajan los artefactos. Las credenciales nunca se escriben en logs.
"""
from __future__ import annotations

import json
import logging
import os
import posixpath
import queue
import shlex
import shutil
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

AlRecibirLinea = Callable[[str], None]
Cancelado = Callable[[], bool]

SONDA_PYTHON = (
    "import json,importlib\n"
    "r={}\n"
    "for m in ('sklearn','torch','tensorflow'):\n"
    "    try:\n"
    "        x=importlib.import_module(m); r[m]=getattr(x,'__version__','?')\n"
    "    except Exception as e:\n"
    "        r[m]=None\n"
    "try:\n"
    "    import torch; r['torch_cuda']=bool(torch.cuda.is_available())\n"
    "except Exception:\n"
    "    r['torch_cuda']=None\n"
    "print('SONDA='+json.dumps(r))\n"
)


class ErrorEjecutor(Exception):
    pass


def interprete_local_por_defecto() -> str:
    """En código fuente, el mismo Python; empaquetado, el `python` del PATH."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python") or shutil.which("py") or ""


class EjecutorLocal:
    modo = "local"

    def __init__(self, interprete: str = ""):
        self.interprete = interprete or interprete_local_por_defecto()

    def describir(self) -> str:
        return f"local ({self.interprete or 'sin intérprete'})"

    def comprobar_conexion(self) -> None:
        if not self.interprete or not (shutil.which(self.interprete) or
                                       Path(self.interprete).is_file()):
            raise ErrorEjecutor(f"No se encuentra el intérprete de Python «{self.interprete}».")

    def ejecutar(self, comando: list[str], cwd: str | Path | None,
                 al_recibir_linea: AlRecibirLinea, cancelado: Cancelado) -> int:
        entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        banderas = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proceso = subprocess.Popen(
                comando, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=entorno,
                creationflags=banderas)
        except OSError as e:
            raise ErrorEjecutor(f"No se pudo lanzar el proceso: {e}") from e

        cola: "queue.Queue[Optional[bytes]]" = queue.Queue()

        def leer():
            assert proceso.stdout is not None
            for linea in iter(proceso.stdout.readline, b""):
                cola.put(linea)
            cola.put(None)

        hilo = threading.Thread(target=leer, daemon=True)
        hilo.start()
        terminado_lectura = False
        while True:
            if cancelado():
                self._terminar(proceso)
                break
            try:
                linea = cola.get(timeout=0.2)
            except queue.Empty:
                continue
            if linea is None:
                terminado_lectura = True
                break
            al_recibir_linea(linea.decode("utf-8", errors="replace").rstrip("\r\n"))
        try:
            codigo = proceso.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._terminar(proceso)
            codigo = proceso.wait(timeout=10)
        if terminado_lectura:
            hilo.join(timeout=2)
        return codigo

    @staticmethod
    def _terminar(proceso: subprocess.Popen) -> None:
        if proceso.poll() is not None:
            return
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()

    def preparar_carpeta(self, local: Path, nombre: str) -> str:
        return str(local)

    def recuperar(self, carpeta_trabajo: str, destino_local: Path) -> None:
        return None  # en local la carpeta de trabajo ya es la de destino

    def cerrar(self) -> None:
        return None


class EjecutorSSH:
    """Ejecución remota en la DGX Spark con paramiko.

    Política de claves de host: se aceptan las conocidas del sistema y las del
    almacén; un host nuevo se acepta la primera vez y se guarda (TOFU). Si la
    clave cambia después, paramiko rechaza la conexión.
    """

    modo = "remoto"

    def __init__(self, host: str, usuario: str, puerto: int = 22,
                 ruta_clave: str = "", contrasena: str = "",
                 interprete: str = "python3",
                 carpeta_remota: str = "~/mova_dgx_trainer/trabajos",
                 known_hosts: Path | None = None, tiempo_conexion: float = 10.0):
        if not host or not usuario:
            raise ErrorEjecutor("Faltan el host o el usuario de la conexión SSH.")
        self.host, self.usuario, self.puerto = host, usuario, int(puerto or 22)
        self.ruta_clave, self._contrasena = ruta_clave, contrasena
        self.interprete = interprete or "python3"
        self.carpeta_remota = carpeta_remota or "~/mova_dgx_trainer/trabajos"
        self.known_hosts = known_hosts
        self.tiempo_conexion = tiempo_conexion
        self._cliente = None

    def describir(self) -> str:
        return f"remoto ({self.usuario}@{self.host}:{self.puerto})"

    def comprobar_conexion(self) -> None:
        self._conectar()

    # --- conexión -----------------------------------------------------------
    def _conectar(self):
        if self._cliente is not None:
            return self._cliente
        import paramiko

        cliente = paramiko.SSHClient()
        try:
            cliente.load_system_host_keys()
        except OSError:
            pass
        if self.known_hosts:
            self.known_hosts.parent.mkdir(parents=True, exist_ok=True)
            self.known_hosts.touch(exist_ok=True)
            cliente.load_host_keys(str(self.known_hosts))
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            cliente.connect(
                self.host, port=self.puerto, username=self.usuario,
                key_filename=self.ruta_clave or None,
                password=self._contrasena or None,
                timeout=self.tiempo_conexion, banner_timeout=self.tiempo_conexion,
                auth_timeout=self.tiempo_conexion,
                look_for_keys=not (self.ruta_clave or self._contrasena),
                allow_agent=True)
        except Exception as e:  # noqa: BLE001
            raise ErrorEjecutor(f"No se pudo conectar a {self.host}: {e}") from e
        if self.known_hosts:
            try:
                cliente.save_host_keys(str(self.known_hosts))
            except OSError:
                log.warning("No se pudo guardar known_hosts en %s", self.known_hosts)
        self._cliente = cliente
        return cliente

    def cerrar(self) -> None:
        if self._cliente is not None:
            self._cliente.close()
            self._cliente = None

    def _home(self) -> str:
        cliente = self._conectar()
        _, salida, _ = cliente.exec_command("printf %s \"$HOME\"", timeout=15)
        return salida.read().decode().strip() or "."

    def _expandir(self, ruta: str) -> str:
        if ruta.startswith("~"):
            return self._home() + ruta[1:]
        return ruta

    # --- ejecución ----------------------------------------------------------
    def ejecutar(self, comando: list[str], cwd: str | Path | None,
                 al_recibir_linea: AlRecibirLinea, cancelado: Cancelado) -> int:
        cliente = self._conectar()
        texto = " ".join(shlex.quote(str(p)) for p in comando)
        if cwd:
            texto = f"cd {shlex.quote(str(cwd))} && {texto}"
        transporte = cliente.get_transport()
        canal = transporte.open_session()
        canal.get_pty()  # al cerrar el canal, el proceso remoto recibe SIGHUP
        canal.exec_command(f"bash -lc {shlex.quote(texto)}")
        pendiente = b""
        while True:
            if cancelado():
                canal.close()
                return 130
            if canal.recv_ready():
                pendiente += canal.recv(65536)
                *lineas, pendiente = pendiente.split(b"\n")
                for l in lineas:
                    al_recibir_linea(l.decode("utf-8", errors="replace").rstrip("\r"))
            elif canal.exit_status_ready() and not canal.recv_ready():
                break
            else:
                time.sleep(0.1)
        if pendiente:
            al_recibir_linea(pendiente.decode("utf-8", errors="replace").rstrip("\r"))
        codigo = canal.recv_exit_status()
        canal.close()
        return codigo

    def preparar_carpeta(self, local: Path, nombre: str) -> str:
        """Sube el contenido de `local` a <carpeta_remota>/<nombre>."""
        cliente = self._conectar()
        base = self._expandir(self.carpeta_remota)
        destino = posixpath.join(base, nombre)
        sftp = cliente.open_sftp()
        try:
            self._mkdir_p(sftp, destino)
            for f in Path(local).iterdir():
                if f.is_file():
                    sftp.put(str(f), posixpath.join(destino, f.name))
        finally:
            sftp.close()
        return destino

    @staticmethod
    def _mkdir_p(sftp, ruta: str) -> None:
        partes, actual = ruta.strip("/").split("/"), "/" if ruta.startswith("/") else ""
        for p in partes:
            actual = posixpath.join(actual, p) if actual else p
            try:
                sftp.stat(actual)
            except OSError:
                sftp.mkdir(actual)

    def recuperar(self, carpeta_trabajo: str, destino_local: Path) -> None:
        cliente = self._conectar()
        sftp = cliente.open_sftp()
        try:
            self._bajar(sftp, carpeta_trabajo, Path(destino_local))
        finally:
            sftp.close()

    def _bajar(self, sftp, remoto: str, local: Path) -> None:
        local.mkdir(parents=True, exist_ok=True)
        for entrada in sftp.listdir_attr(remoto):
            origen = posixpath.join(remoto, entrada.filename)
            if stat.S_ISDIR(entrada.st_mode or 0):
                self._bajar(sftp, origen, local / entrada.filename)
            else:
                sftp.get(origen, str(local / entrada.filename))


def crear_ejecutor(config: dict, known_hosts: Path | None = None):
    """Fábrica a partir de la configuración guardada en la app."""
    if (config or {}).get("modo") == "remoto":
        return EjecutorSSH(
            host=config.get("host", ""), usuario=config.get("usuario", ""),
            puerto=int(config.get("puerto") or 22),
            ruta_clave=config.get("ruta_clave", ""),
            contrasena=config.get("contrasena", ""),
            interprete=config.get("interprete_remoto", "python3"),
            carpeta_remota=config.get("carpeta_remota", "~/mova_dgx_trainer/trabajos"),
            known_hosts=known_hosts)
    return EjecutorLocal(config.get("interprete_local", "") if config else "")


def comprobar_entorno(ejecutor, cancelado: Cancelado = lambda: False) -> list[dict]:
    """nvidia-smi, python -V e import de torch/tensorflow/sklearn.

    Devuelve filas {componente, disponible, version}. Lo no detectado lleva
    version = None (la UI lo marca como [PENDIENTE]).

    En remoto se conecta antes: si la máquina no responde se lanza ErrorEjecutor,
    en vez de devolver todo como «no detectado» (parecería que falta software).
    """
    if ejecutor.modo == "remoto":
        ejecutor.comprobar_conexion()
    filas: list[dict] = []

    def capturar(comando: list[str]) -> tuple[int, list[str]]:
        lineas: list[str] = []
        try:
            codigo = ejecutor.ejecutar(comando, None, lineas.append, cancelado)
        except (ErrorEjecutor, OSError) as e:
            return 127, [str(e)]
        return codigo, lineas

    codigo, lineas = capturar(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                               "--format=csv,noheader"])
    gpu = lineas[0].strip() if codigo == 0 and lineas else None
    filas.append({"componente": "GPU (nvidia-smi)", "disponible": gpu is not None,
                  "version": gpu})

    codigo, lineas = capturar([ejecutor.interprete, "-V"])
    py = next((l.strip() for l in lineas if l.lower().startswith("python")), None)
    filas.append({"componente": "Python", "disponible": codigo == 0 and py is not None,
                  "version": py if codigo == 0 else None})

    sonda: dict = {}
    if codigo == 0:
        _, lineas = capturar([ejecutor.interprete, "-c", SONDA_PYTHON])
        for l in lineas:
            if l.startswith("SONDA="):
                try:
                    sonda = json.loads(l[len("SONDA="):])
                except ValueError:
                    sonda = {}
    for clave, nombre in (("sklearn", "scikit-learn"), ("torch", "PyTorch"),
                          ("tensorflow", "TensorFlow")):
        v = sonda.get(clave)
        filas.append({"componente": nombre, "disponible": v is not None, "version": v})
    if sonda.get("torch_cuda") is not None:
        filas.append({"componente": "PyTorch con CUDA", "disponible": bool(sonda["torch_cuda"]),
                      "version": "sí" if sonda["torch_cuda"] else None})
    return filas
