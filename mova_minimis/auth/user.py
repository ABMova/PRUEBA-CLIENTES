"""Usuarios: hash de contraseñas (PBKDF2-HMAC-SHA256 con sal propia) y cifrado de secretos."""
import base64
import hashlib
import hmac
import os
import re

import config

ITERACIONES = 390_000


def hash_clave(clave: str) -> str:
    sal = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${base64.b64encode(sal).decode()}${base64.b64encode(dk).decode()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        alg, it, sal_b64, dk_b64 = guardado.split("$")
        if alg != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), base64.b64decode(sal_b64), int(it))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def problemas_clave(clave: str) -> list[str]:
    """Reglas mínimas para una contraseña nueva."""
    fallos = []
    if len(clave) < 10:
        fallos.append("al menos 10 caracteres")
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", clave) or not re.search(r"\d", clave):
        fallos.append("letras y números")
    if clave == config.ADMIN_INICIAL_CLAVE:
        fallos.append("distinta de la contraseña provisional")
    return fallos


# ---------------------------------------------------------------- cifrado de secretos
def _fernet():
    from cryptography.fernet import Fernet
    ruta = config.FICHERO_CLAVE_CIFRADO
    if not ruta.exists():
        ruta.write_bytes(Fernet.generate_key())
    return Fernet(ruta.read_bytes().strip())


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode("utf-8")).decode()


def descifrar(token: str) -> str | None:
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(token.encode()).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def cifrar_bytes(datos: bytes) -> bytes:
    return _fernet().encrypt(datos)


def descifrar_bytes(datos: bytes) -> bytes:
    return _fernet().decrypt(datos)


def enmascarar(secreto: str | None) -> str:
    return "..." + secreto[-4:] if secreto and len(secreto) >= 8 else ""
