"""Prueba 3 - el esquema es idempotente y crea todas las tablas.

Se ejecuta sobre una base de datos vacia y temporal: no toca la de produccion.

    .venv\\Scripts\\python.exe pruebas\\test_esquema.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

TEMPORAL = Path(tempfile.mkdtemp(prefix="mova-esquema-"))
os.environ["MOVA_DATOS"] = str(TEMPORAL)

import config  # noqa: E402
from datos import repositorio  # noqa: E402

TABLAS_ESPERADAS = {
    "usuarios", "sesiones", "boletines", "palabras_clave", "ejecuciones", "logs_scraping",
    "publicaciones", "descartes", "tokens_descarte", "destinatarios", "envios", "ajustes",
    "auditoria", "intentos_ip",
}

fallos: list[str] = []


def comprobar(condicion: bool, mensaje: str) -> None:
    print(f"  {'OK   ' if condicion else 'FALLO'} {mensaje}")
    if not condicion:
        fallos.append(mensaje)


def main() -> int:
    print(f"Base de datos de prueba: {config.RUTA_BD}")
    comprobar(not config.RUTA_BD.exists(), "se parte de una base de datos vacia")

    print("\n1) Primera aplicacion del esquema")
    repositorio.aplicar_esquema()
    tablas_1 = set(repositorio.tablas())
    faltan = TABLAS_ESPERADAS - tablas_1
    comprobar(not faltan, f"estan las {len(TABLAS_ESPERADAS)} tablas esperadas"
                          + (f" (faltan: {sorted(faltan)})" if faltan else ""))

    boletines_1 = repositorio.boletines()
    palabras_1 = repositorio.palabras_clave(solo_activas=False)
    destinatarios_1 = repositorio.destinatarios(solo_activos=False)
    comprobar(len(boletines_1) == 8, f"8 boletines precargados: BOE y 7 autonomicos (hay {len(boletines_1)})")
    comprobar(len([p for p in palabras_1 if not p["refuerzo"]]) == 25,
              "25 palabras clave de filtro precargadas")
    comprobar({d["correo"] for d in destinatarios_1} == {"antonio@mova.es", "j.javier@mova.es"},
              "destinatarios iniciales precargados")

    print("\n2) Segunda aplicacion del esquema (idempotencia)")
    repositorio.aplicar_esquema()
    tablas_2 = set(repositorio.tablas())
    comprobar(tablas_1 == tablas_2, "las tablas no cambian al reaplicar el esquema")
    comprobar(len(repositorio.boletines()) == 8, "los boletines no se duplican (BOE y 7 autonomicos)")
    comprobar(len(repositorio.palabras_clave(solo_activas=False)) == len(palabras_1),
              "las palabras clave no se duplican")
    comprobar(len(repositorio.destinatarios(solo_activos=False)) == len(destinatarios_1),
              "los destinatarios no se duplican")

    print("\n3) Datos existentes sobreviven a reaplicar el esquema")
    repositorio.guardar_ajuste("hora_ejecucion", "08:15")
    repositorio.aplicar_esquema()
    comprobar(repositorio.ajuste("hora_ejecucion") == "08:15",
              "un ajuste modificado sigue igual tras reaplicar")

    print("\n4) Claves foraneas e indices activos")
    filas = repositorio.conexion().execute("PRAGMA foreign_keys").fetchone()
    comprobar(bool(filas[0]), "claves foraneas activas")
    indices = repositorio.conexion().execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'").fetchone()[0]
    comprobar(indices >= 12, f"indices creados ({indices})")

    print("\n5) Cifrado de credenciales")
    repositorio.guardar_ajuste("anthropic_api_key", "sk-ant-ejemplo-123")
    crudo = repositorio.conexion().execute(
        "SELECT valor FROM ajustes WHERE clave='anthropic_api_key'").fetchone()[0]
    comprobar(crudo != "sk-ant-ejemplo-123" and crudo != "",
              "la clave se guarda cifrada, no en claro")
    comprobar(repositorio.ajuste("anthropic_api_key") == "sk-ant-ejemplo-123",
              "la clave se recupera descifrada")

    print("\n6) Usuario inicial y contrasenas")
    provisional = repositorio.asegurar_admin_inicial()
    admin = repositorio.usuario_por_nombre("admin")
    comprobar(admin is not None and bool(admin["cambio_obligatorio"]),
              "el usuario admin nace con cambio de contrasena obligatorio")
    comprobar(admin["hash_clave"] != provisional and admin["iteraciones"] == 200000,
              "la contrasena se guarda con PBKDF2 y 200.000 iteraciones")
    comprobar(repositorio.verificar_clave(admin, provisional), "la contrasena provisional valida")
    comprobar(not repositorio.verificar_clave(admin, provisional + "x"),
              "una contrasena incorrecta no valida")

    print(f"\n{'TODAS LAS COMPROBACIONES PASAN' if not fallos else 'FALLOS: ' + str(fallos)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
