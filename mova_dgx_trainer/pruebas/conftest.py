import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pruebas.recursos.generar import generar  # noqa: E402


@pytest.fixture(scope="session")
def recursos() -> dict:
    return generar()


@pytest.fixture
def almacen(tmp_path):
    from infra.rutas import Almacen
    return Almacen(tmp_path / "almacen").crear()
