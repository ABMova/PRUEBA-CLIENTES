"""Repositorio: el ÚNICO módulo con SQL. Servicios y UI pasan siempre por aquí.

Cada operación abre su propia conexión, de modo que se puede usar desde los
hilos de trabajo sin compartir conexiones entre hilos.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from datos import migraciones
from datos.esquema import TABLAS

COLUMNAS_EJECUCION_EDITABLES = {
    "estado", "comando", "hiperparametros_json", "versiones_json", "curva_json",
    "ruta_modelo", "ruta_log", "duracion_s", "veredicto", "detalle_veredicto_json", "error",
    "terminada", "modo",
}


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(valor: Any) -> str:
    return json.dumps(valor if valor is not None else {}, ensure_ascii=False, default=str)


def _fila(fila: sqlite3.Row | None) -> dict | None:
    if fila is None:
        return None
    d = dict(fila)
    for clave in list(d):
        if clave.endswith("_json") or clave == "estado_pipeline":
            destino = clave[:-5] if clave.endswith("_json") else clave
            try:
                d[destino] = json.loads(d[clave]) if d[clave] else {}
            except (TypeError, ValueError):
                d[destino] = {}
    return d


class Repositorio:
    def __init__(self, ruta_bd: Path):
        self.ruta = Path(ruta_bd)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as c:
            c.execute("PRAGMA journal_mode=WAL")
            self.migracion = migraciones.aplicar(c)

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(str(self.ruta), timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            with c:
                yield c
        finally:
            c.close()

    def version_esquema(self) -> int:
        with self._conexion() as c:
            return migraciones.version(c)

    # --- proyectos ------------------------------------------------------------
    def crear_proyecto(self, nombre: str, tipo_tarea: str, descripcion: str = "") -> int:
        with self._conexion() as c:
            cur = c.execute(
                "INSERT INTO proyectos(nombre, tipo_tarea, descripcion, creado, actualizado,"
                " estado_pipeline) VALUES (?,?,?,?,?,?)",
                (nombre, tipo_tarea, descripcion, ahora(), ahora(),
                 _json({"paso_actual": "importacion", "completados": ["proyecto"]})))
            return int(cur.lastrowid)

    def existe_proyecto(self, nombre: str) -> bool:
        with self._conexion() as c:
            return c.execute("SELECT 1 FROM proyectos WHERE nombre=?", (nombre,)).fetchone() is not None

    def obtener_proyecto(self, proyecto_id: int) -> dict | None:
        with self._conexion() as c:
            return _fila(c.execute("SELECT * FROM proyectos WHERE id=?", (proyecto_id,)).fetchone())

    def listar_proyectos(self) -> list[dict]:
        with self._conexion() as c:
            return [_fila(f) for f in c.execute(
                "SELECT * FROM proyectos ORDER BY actualizado DESC, id DESC")]

    def guardar_estado_pipeline(self, proyecto_id: int, estado: dict) -> None:
        with self._conexion() as c:
            c.execute("UPDATE proyectos SET estado_pipeline=?, actualizado=? WHERE id=?",
                      (_json(estado), ahora(), proyecto_id))

    # --- ficheros de origen -----------------------------------------------------
    def registrar_fichero(self, proyecto_id: int, ruta: str, nombre: str, formato: str,
                          tamano: int, filas: int | None, columnas: int | None,
                          hash_: str | None, codificacion: str | None,
                          delimitador: str | None, hoja: str | None, estado: str,
                          avisos: list) -> int:
        with self._conexion() as c:
            cur = c.execute(
                "INSERT INTO ficheros_origen(proyecto_id, ruta, nombre, formato, tamano, filas,"
                " columnas, hash, codificacion, delimitador, hoja, estado, avisos_json, importado)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (proyecto_id, ruta, nombre, formato, tamano, filas, columnas, hash_,
                 codificacion, delimitador, hoja, estado, _json(avisos), ahora()))
            return int(cur.lastrowid)

    def listar_ficheros(self, proyecto_id: int) -> list[dict]:
        with self._conexion() as c:
            return [_fila(f) for f in c.execute(
                "SELECT * FROM ficheros_origen WHERE proyecto_id=? ORDER BY id", (proyecto_id,))]

    # --- datasets -------------------------------------------------------------------
    def crear_dataset(self, proyecto_id: int, fase: str, nombre: str, ruta: str,
                      filas: int, columnas: int, hash_: str, objetivo: str | None = None,
                      division: dict | None = None, preparacion: dict | None = None) -> int:
        with self._conexion() as c:
            cur = c.execute(
                "INSERT INTO datasets(proyecto_id, fase, nombre, ruta, filas, columnas, hash,"
                " objetivo, division_json, preparacion_json, creado) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (proyecto_id, fase, nombre, ruta, filas, columnas, hash_, objetivo,
                 _json(division), _json(preparacion), ahora()))
            return int(cur.lastrowid)

    def obtener_dataset(self, dataset_id: int) -> dict | None:
        with self._conexion() as c:
            return _fila(c.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone())

    def ultimo_dataset(self, proyecto_id: int, fase: str) -> dict | None:
        with self._conexion() as c:
            return _fila(c.execute(
                "SELECT * FROM datasets WHERE proyecto_id=? AND fase=? ORDER BY id DESC LIMIT 1",
                (proyecto_id, fase)).fetchone())

    # --- configuraciones --------------------------------------------------------------
    def crear_configuracion(self, proyecto_id: int, framework: str, script: str,
                            hiperparametros: dict, umbrales: dict, metrica_objetivo: str,
                            max_reintentos: int, semilla: int) -> int:
        with self._conexion() as c:
            cur = c.execute(
                "INSERT INTO configuraciones(proyecto_id, framework, script, hiperparametros_json,"
                " umbrales_json, metrica_objetivo, max_reintentos, semilla, creado)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (proyecto_id, framework, script, _json(hiperparametros), _json(umbrales),
                 metrica_objetivo, int(max_reintentos), int(semilla), ahora()))
            return int(cur.lastrowid)

    def obtener_configuracion(self, configuracion_id: int) -> dict | None:
        with self._conexion() as c:
            return _fila(c.execute("SELECT * FROM configuraciones WHERE id=?",
                                   (configuracion_id,)).fetchone())

    def ultima_configuracion(self, proyecto_id: int) -> dict | None:
        with self._conexion() as c:
            return _fila(c.execute(
                "SELECT * FROM configuraciones WHERE proyecto_id=? ORDER BY id DESC LIMIT 1",
                (proyecto_id,)).fetchone())

    # --- ejecuciones -------------------------------------------------------------------
    def crear_ejecucion(self, proyecto_id: int, configuracion_id: int, dataset_id: int,
                        intento: int, padre_id: int | None, motivo: str, modo: str,
                        hiperparametros: dict) -> int:
        with self._conexion() as c:
            cur = c.execute(
                "INSERT INTO ejecuciones(proyecto_id, configuracion_id, dataset_id, intento,"
                " padre_id, motivo, estado, modo, hiperparametros_json, iniciada)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (proyecto_id, configuracion_id, dataset_id, intento, padre_id, motivo,
                 "en_curso", modo, _json(hiperparametros), ahora()))
            return int(cur.lastrowid)

    def actualizar_ejecucion(self, ejecucion_id: int, **campos: Any) -> None:
        desconocidas = set(campos) - COLUMNAS_EJECUCION_EDITABLES
        if desconocidas:
            raise ValueError(f"Columnas no editables: {sorted(desconocidas)}")
        if not campos:
            return
        valores = [(_json(v) if k.endswith("_json") else v) for k, v in campos.items()]
        asignaciones = ", ".join(f"{k}=?" for k in campos)
        with self._conexion() as c:
            c.execute(f"UPDATE ejecuciones SET {asignaciones} WHERE id=?",
                      (*valores, ejecucion_id))

    def obtener_ejecucion(self, ejecucion_id: int) -> dict | None:
        with self._conexion() as c:
            return _fila(c.execute("SELECT * FROM ejecuciones WHERE id=?",
                                   (ejecucion_id,)).fetchone())

    def listar_ejecuciones(self, proyecto_id: int) -> list[dict]:
        with self._conexion() as c:
            return [_fila(f) for f in c.execute(
                "SELECT * FROM ejecuciones WHERE proyecto_id=? ORDER BY id", (proyecto_id,))]

    def marcar_ejecuciones_interrumpidas(self) -> int:
        """Al arrancar: lo que quedó 'en_curso' de una sesión anterior se marca."""
        with self._conexion() as c:
            cur = c.execute("UPDATE ejecuciones SET estado='interrumpida', terminada=?"
                            " WHERE estado='en_curso'", (ahora(),))
            return cur.rowcount

    # --- métricas ----------------------------------------------------------------------
    def guardar_metricas(self, proyecto_id: int, metricas: dict, origen: str, conjunto: str,
                         dataset_id: int | None = None, ejecucion_id: int | None = None) -> None:
        filas = []
        for nombre, valor in metricas.items():
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                filas.append((proyecto_id, dataset_id, ejecucion_id, origen, conjunto,
                              nombre, float(valor), None))
            else:
                filas.append((proyecto_id, dataset_id, ejecucion_id, origen, conjunto,
                              nombre, None, _json(valor)))
        with self._conexion() as c:
            c.executemany(
                "INSERT INTO metricas(proyecto_id, dataset_id, ejecucion_id, origen, conjunto,"
                " nombre, valor, detalle_json) VALUES (?,?,?,?,?,?,?,?)", filas)

    def obtener_metricas(self, origen: str, ejecucion_id: int | None = None,
                         dataset_id: int | None = None, conjunto: str = "test") -> dict:
        sql = "SELECT nombre, valor, detalle_json FROM metricas WHERE origen=? AND conjunto=?"
        args: list[Any] = [origen, conjunto]
        if ejecucion_id is not None:
            sql += " AND ejecucion_id=?"
            args.append(ejecucion_id)
        if dataset_id is not None:
            sql += " AND dataset_id=?"
            args.append(dataset_id)
        sql += " ORDER BY id"
        resultado: dict = {}
        with self._conexion() as c:
            for f in c.execute(sql, args):
                if f["valor"] is not None:
                    resultado[f["nombre"]] = f["valor"]
                else:
                    resultado[f["nombre"]] = json.loads(f["detalle_json"]) if f["detalle_json"] else None
        return resultado

    # --- logs ----------------------------------------------------------------------------
    def anadir_logs(self, proyecto_id: int | None, ejecucion_id: int | None,
                    lineas: Iterable[tuple[str, str, str]]) -> None:
        """lineas: (momento, nivel, texto)."""
        with self._conexion() as c:
            c.executemany(
                "INSERT INTO logs(proyecto_id, ejecucion_id, momento, nivel, texto)"
                " VALUES (?,?,?,?,?)",
                [(proyecto_id, ejecucion_id, m, n, t) for m, n, t in lineas])

    def anadir_log(self, proyecto_id: int | None, ejecucion_id: int | None,
                   nivel: str, texto: str) -> None:
        self.anadir_logs(proyecto_id, ejecucion_id, [(ahora(), nivel, texto)])

    def listar_logs(self, ejecucion_id: int) -> list[dict]:
        with self._conexion() as c:
            return [dict(f) for f in c.execute(
                "SELECT momento, nivel, texto FROM logs WHERE ejecucion_id=? ORDER BY id",
                (ejecucion_id,))]

    # --- informes --------------------------------------------------------------------------
    def registrar_informe(self, proyecto_id: int, ruta_docx: str, ruta_pdf: str,
                          hash_docx: str, hash_pdf: str) -> int:
        with self._conexion() as c:
            cur = c.execute(
                "INSERT INTO informes(proyecto_id, ruta_docx, ruta_pdf, hash_docx, hash_pdf, creado)"
                " VALUES (?,?,?,?,?,?)",
                (proyecto_id, ruta_docx, ruta_pdf, hash_docx, hash_pdf, ahora()))
            return int(cur.lastrowid)

    def listar_informes(self, proyecto_id: int) -> list[dict]:
        with self._conexion() as c:
            return [dict(f) for f in c.execute(
                "SELECT * FROM informes WHERE proyecto_id=? ORDER BY id DESC", (proyecto_id,))]

    # --- exportación genérica ----------------------------------------------------------------
    def leer_tabla(self, tabla: str, proyecto_id: int | None = None) -> tuple[list[str], list[tuple]]:
        if tabla not in TABLAS:
            raise ValueError(f"Tabla desconocida: {tabla}")
        sql = f"SELECT * FROM {tabla}"
        args: tuple = ()
        if proyecto_id is not None:
            sql += " WHERE " + ("id=?" if tabla == "proyectos" else "proyecto_id=?")
            args = (proyecto_id,)
        with self._conexion() as c:
            cur = c.execute(sql + " ORDER BY id", args)
            columnas = [d[0] for d in cur.description]
            return columnas, [tuple(f) for f in cur.fetchall()]
