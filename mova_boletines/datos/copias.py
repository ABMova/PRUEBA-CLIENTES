"""Copias de seguridad de la base de datos.

Se usa la API backup() de SQLite: funciona con la aplicacion en marcha, respeta
el modo WAL y no deja la copia a medias.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import config
from datos import repositorio


def _nombre_copia(motivo: str) -> str:
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"mova-{marca}-{motivo}.db"


def crear_copia(motivo: str = "manual", usuario: str = "sistema") -> Path:
    config.preparar_carpetas()
    destino = config.RUTA_COPIAS / _nombre_copia(motivo)
    origen = repositorio.conexion()
    con_destino = sqlite3.connect(destino)
    try:
        origen.backup(con_destino)
    finally:
        con_destino.close()
    rotar()
    repositorio.registrar_auditoria(usuario, "copia_seguridad", destino.name, f"motivo={motivo}")
    return destino


def rotar() -> None:
    maximo = repositorio.ajuste_int("copias_max", 10)
    copias = sorted(config.RUTA_COPIAS.glob("mova-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for sobrante in copias[maximo:]:
        try:
            sobrante.unlink()
        except OSError:
            pass


def listar() -> list[dict]:
    copias = sorted(config.RUTA_COPIAS.glob("mova-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "nombre": copia.name,
            "tamano_kb": round(copia.stat().st_size / 1024, 1),
            "fecha": datetime.fromtimestamp(copia.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
        }
        for copia in copias
    ]


def restaurar(nombre: str, usuario: str = "sistema") -> tuple[bool, str]:
    """Restaura una copia. Antes guarda el estado actual, por si acaso."""
    origen = config.RUTA_COPIAS / nombre
    if not origen.exists() or origen.parent != config.RUTA_COPIAS:
        return False, "La copia indicada no existe"
    try:
        crear_copia("previa-restauracion", usuario)
    except sqlite3.Error as error:
        return False, f"No se pudo guardar el estado actual: {error}"

    repositorio.cerrar_conexion()
    try:
        for sufijo in ("-wal", "-shm"):
            auxiliar = Path(str(config.RUTA_BD) + sufijo)
            if auxiliar.exists():
                auxiliar.unlink()
        shutil.copy2(origen, config.RUTA_BD)
    except OSError as error:
        return False, f"No se pudo restaurar: {error}"

    repositorio.aplicar_esquema()
    repositorio.registrar_auditoria(usuario, "restaurar_copia", nombre, "Restauracion completada")
    return True, f"Copia {nombre} restaurada"


def exportar_json() -> Path:
    config.preparar_carpetas()
    destino = config.RUTA_ADJUNTOS / f"publicaciones-{datetime.now():%Y%m%d-%H%M%S}.json"
    datos = repositorio.exportar_publicaciones()
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def exportar_excel() -> Path:
    from openpyxl import Workbook

    config.preparar_carpetas()
    destino = config.RUTA_ADJUNTOS / f"publicaciones-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
    datos = repositorio.exportar_publicaciones()
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Publicaciones"
    cabeceras = list(datos[0].keys()) if datos else [
        "id", "codigo_boletin", "comunidad", "fecha_publicacion", "titulo"]
    hoja.append(cabeceras)
    for fila in datos:
        hoja.append([fila.get(col, "") for col in cabeceras])
    for indice, columna in enumerate(cabeceras, start=1):
        hoja.column_dimensions[hoja.cell(row=1, column=indice).column_letter].width = min(
            60, max(14, len(columna) + 4))
    libro.save(destino)
    return destino
