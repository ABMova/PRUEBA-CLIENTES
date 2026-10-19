"""Cifrado local con Fernet sobre una clave derivada de la máquina.

La clave no se guarda: se deriva con PBKDF2 a partir del identificador de la
máquina (MachineGuid en Windows) y una sal aleatoria guardada en el almacén.
Un fichero cifrado copiado a otro equipo no se puede abrir allí.
"""
from __future__ import annotations

import base64
import json
import os
import platform
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERACIONES = 390_000


class ErrorCifrado(Exception):
    pass


def identificador_maquina() -> str:
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                valor, _ = winreg.QueryValueEx(k, "MachineGuid")
                return str(valor)
        except OSError:
            pass
    for ruta in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(ruta).read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return f"{platform.node()}-{uuid.getnode()}"


class Cifrador:
    def __init__(self, carpeta_config: Path):
        self.carpeta = Path(carpeta_config)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._derivar_clave())

    def _sal(self) -> bytes:
        ruta = self.carpeta / "sal.bin"
        if ruta.exists():
            return ruta.read_bytes()
        sal = os.urandom(16)
        ruta.write_bytes(sal)
        return sal

    def _derivar_clave(self) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=self._sal(), iterations=ITERACIONES)
        return base64.urlsafe_b64encode(kdf.derive(identificador_maquina().encode()))

    def cifrar(self, texto: str) -> bytes:
        return self._fernet.encrypt(texto.encode("utf-8"))

    def descifrar(self, datos: bytes) -> str:
        try:
            return self._fernet.decrypt(datos).decode("utf-8")
        except InvalidToken as e:
            raise ErrorCifrado("No se puede descifrar: el fichero es de otra "
                               "máquina o está dañado.") from e

    def guardar_json(self, nombre: str, datos: dict) -> Path:
        ruta = self.carpeta / nombre
        ruta.write_bytes(self.cifrar(json.dumps(datos, ensure_ascii=False)))
        return ruta

    def cargar_json(self, nombre: str) -> dict:
        ruta = self.carpeta / nombre
        if not ruta.exists():
            return {}
        return json.loads(self.descifrar(ruta.read_bytes()))
