"""Rutas de la aplicación: recursos empaquetados y ALMACEN de datos de usuario.

OJO: el paquete `datos/` es CÓDIGO (esquema, repositorio, migraciones, copias).
Los datos del usuario viven en `almacen/`, junto al ejecutable. Si ahí no se puede
escribir, se usa %LOCALAPPDATA%\\MOVA\\DGXSparkTrainer\\almacen\\ y se anota en el
log de arranque. La ubicación no es configurable por el usuario.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


def es_empaquetado() -> bool:
    return bool(getattr(sys, "frozen", False))


def raiz_proyecto() -> Path:
    """Carpeta raíz del código fuente (la que contiene main.py)."""
    return Path(__file__).resolve().parent.parent


def base_recursos() -> Path:
    """Donde están ui/estilos, ui/recursos y scripts_entrenamiento."""
    if es_empaquetado():
        return Path(getattr(sys, "_MEIPASS"))
    return raiz_proyecto()


def carpeta_ejecutable() -> Path:
    if es_empaquetado():
        return Path(sys.executable).resolve().parent
    return raiz_proyecto()


def ruta_recurso(*partes: str) -> Path:
    return base_recursos().joinpath(*partes)


def carpeta_scripts() -> Path:
    return ruta_recurso("scripts_entrenamiento")


def _se_puede_escribir(carpeta: Path) -> bool:
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / f".prueba_{uuid.uuid4().hex}"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return True
    except OSError:
        return False


def carpeta_alternativa() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MOVA" / "DGXSparkTrainer" / "almacen"


@dataclass(frozen=True)
class Almacen:
    raiz: Path
    nota: str = ""

    @property
    def bd(self) -> Path:
        return self.raiz / "bd" / "trainer.db"

    @property
    def backups(self) -> Path:
        return self.raiz / "backups"

    @property
    def modelos(self) -> Path:
        return self.raiz / "modelos"

    @property
    def logs(self) -> Path:
        return self.raiz / "logs"

    @property
    def informes(self) -> Path:
        return self.raiz / "informes"

    @property
    def datasets(self) -> Path:
        return self.raiz / "datasets"

    @property
    def config(self) -> Path:
        return self.raiz / "config"

    def crear(self) -> "Almacen":
        for c in (self.bd.parent, self.backups, self.modelos, self.logs,
                  self.informes, self.datasets, self.config):
            c.mkdir(parents=True, exist_ok=True)
        return self


def resolver_almacen() -> Almacen:
    """Junto al ejecutable; si no se puede escribir, en LOCALAPPDATA (con nota)."""
    preferida = carpeta_ejecutable() / "almacen"
    if _se_puede_escribir(preferida):
        return Almacen(preferida).crear()
    alternativa = carpeta_alternativa()
    nota = (f"No se puede escribir en {preferida}; el almacén se ha situado en "
            f"{alternativa}.")
    return Almacen(alternativa, nota).crear()
