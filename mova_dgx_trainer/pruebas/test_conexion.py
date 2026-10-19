"""Sin conexión con la Spark, el aviso tiene que decirlo (no «no detectado» en todo)."""
import socket

import pytest

from infra.cifrado import Cifrador
from infra.ejecutor_ssh import EjecutorLocal, EjecutorSSH, ErrorEjecutor, comprobar_entorno
from nucleo.contexto import Contexto
from nucleo.coordinador import Coordinador, ErrorServicio


def _puerto_cerrado() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()  # nadie escucha: la conexión se rechaza al momento
    return puerto


def _ssh_inalcanzable(tmp_path) -> EjecutorSSH:
    return EjecutorSSH("127.0.0.1", "mova_ia", puerto=_puerto_cerrado(),
                       contrasena="no-se-usa", known_hosts=tmp_path / "kh", tiempo_conexion=3)


def test_comprobar_entorno_remoto_sin_conexion_lanza_error(tmp_path):
    with pytest.raises(ErrorEjecutor, match="No se pudo conectar"):
        comprobar_entorno(_ssh_inalcanzable(tmp_path))


def test_coordinador_explica_el_fallo_de_conexion(almacen, tmp_path):
    coord = Coordinador(almacen, Cifrador(almacen.config))
    with pytest.raises(ErrorServicio) as e:
        coord.comprobar_entorno(Contexto(), _ssh_inalcanzable(tmp_path))
    assert "No se puede conectar con 127.0.0.1" in e.value.que_paso
    assert "Tailscale" in e.value.que_hacer


def test_interprete_local_inexistente():
    with pytest.raises(ErrorEjecutor, match="intérprete"):
        EjecutorLocal("C:/no/existe/python.exe").comprobar_conexion()
