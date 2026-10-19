"""Coordinador: ciclo de vida del proyecto, estado del pipeline, orquestación y reanudación.

Es la capa de servicios: la UI solo habla con el Coordinador, y el Coordinador
con el repositorio (SQL) y con los demás módulos del núcleo.
"""
from __future__ import annotations

import logging
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

from datos import backup
from datos.repositorio import Repositorio
from infra.rutas import Almacen, carpeta_scripts
from nucleo import entrenador, evaluador, exportador, importador, preparador, reintentos
from nucleo.contexto import Cancelado, Contexto
from nucleo.rejillas import (INICIALES, INICIALES_RED, METRICAS_OBJETIVO, TIPOS_TAREA,
                             TIPO_PENDIENTE, es_clasificacion)

log = logging.getLogger(__name__)

PASOS = ["proyecto", "importacion", "dataset", "entrenamiento", "resultados", "informe"]
NOMBRE_CONEXION = "conexion.enc"


class ErrorServicio(Exception):
    """Error accionable: `que_paso` y `que_hacer` van al QMessageBox."""

    def __init__(self, que_paso: str, que_hacer: str):
        self.que_paso, self.que_hacer = que_paso, que_hacer
        super().__init__(f"{que_paso} {que_hacer}")


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", texto).strip("_")[:40] or "proyecto"


class Coordinador:
    def __init__(self, almacen: Almacen, cifrador=None):
        self.almacen = almacen.crear()
        self.repo = Repositorio(almacen.bd)
        self.cifrador = cifrador
        self._brutos: dict[int, pd.DataFrame] = {}
        self._lotes: dict[int, importador.ResumenLote] = {}

    # --- arranque, copias y tablas ---------------------------------------------------
    def al_arrancar(self) -> dict:
        copia = backup.crear_copia(self.almacen.bd, self.almacen.backups, "arranque")
        interrumpidas = self.repo.marcar_ejecuciones_interrumpidas()
        return {"copia": str(copia) if copia else None, "interrumpidas": interrumpidas,
                "migracion": self.repo.migracion}

    def crear_copia(self) -> Path | None:
        return backup.crear_copia(self.almacen.bd, self.almacen.backups, "manual")

    def listar_copias(self) -> list[Path]:
        return backup.listar(self.almacen.backups)

    def restaurar_copia(self, copia: Path) -> Path | None:
        self._brutos.clear()
        return backup.restaurar(Path(copia), self.almacen.bd, self.almacen.backups)

    def tabla(self, nombre: str, proyecto_id: int | None = None) -> tuple[list[str], list[tuple]]:
        return self.repo.leer_tabla(nombre, proyecto_id)

    @staticmethod
    def exportar_tabla(cabecera: list[str], filas: list[list], ruta: Path) -> Path:
        return exportador.exportar_tabla(cabecera, filas, ruta)

    # --- conexión (cifrada) ------------------------------------------------------------
    def cargar_conexion(self) -> dict:
        por_defecto = {"modo": "local", "interprete_local": "", "host": "", "puerto": 22,
                       "usuario": "", "ruta_clave": "", "contrasena": "",
                       "interprete_remoto": "python3",
                       "carpeta_remota": "~/mova_dgx_trainer/trabajos"}
        if not self.cifrador:
            return por_defecto
        try:
            return {**por_defecto, **self.cifrador.cargar_json(NOMBRE_CONEXION)}
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo leer la conexión cifrada: %s", e)
            return por_defecto

    def guardar_conexion(self, datos: dict) -> None:
        if not self.cifrador:
            raise ErrorServicio("No hay cifrador disponible.", "Reinicie la aplicación.")
        self.cifrador.guardar_json(NOMBRE_CONEXION, datos)

    def crear_ejecutor(self):
        from infra.ejecutor_ssh import crear_ejecutor
        return crear_ejecutor(self.cargar_conexion(), self.almacen.config / "known_hosts")

    @staticmethod
    def _error_conexion(ejecutor, e: Exception) -> ErrorServicio:
        if ejecutor.modo == "remoto":
            return ErrorServicio(
                f"No se puede conectar con {ejecutor.host} ({e})",
                "Compruebe que está en la red de la oficina o que Tailscale está encendido, "
                "y revise host, usuario y clave en Configuración")
        return ErrorServicio(str(e), "Indique un intérprete de Python válido en Configuración")

    def comprobar_entorno(self, ctx: Contexto, ejecutor=None) -> dict:
        from infra.ejecutor_ssh import ErrorEjecutor, comprobar_entorno
        ejecutor = ejecutor or self.crear_ejecutor()
        ctx.log(f"Comprobando entorno en {ejecutor.describir()}…")
        try:
            filas = comprobar_entorno(ejecutor, ctx.cancelado)
        except ErrorEjecutor as e:
            raise self._error_conexion(ejecutor, e) from e
        finally:
            ejecutor.cerrar()
        for f in filas:
            ctx.log(f"  {f['componente']}: {f['version'] or 'no detectado'}")
        return {"filas": filas, "modo": ejecutor.describir()}

    # --- proyectos y estado del pipeline --------------------------------------------------
    @staticmethod
    def tipos_tarea() -> list[tuple[str, str, bool]]:
        return [(k, v, True) for k, v in TIPOS_TAREA.items()] + [(*TIPO_PENDIENTE, False)]

    def crear_proyecto(self, nombre: str, tipo_tarea: str, descripcion: str = "") -> int:
        nombre = (nombre or "").strip()
        if not nombre:
            raise ErrorServicio("El proyecto necesita un nombre.", "Escriba un nombre y vuelva a crear.")
        if tipo_tarea not in TIPOS_TAREA:
            raise ErrorServicio(f"El tipo de tarea «{tipo_tarea}» no está disponible.",
                                "Elija uno de los tipos habilitados en el desplegable.")
        if self.repo.existe_proyecto(nombre):
            raise ErrorServicio(f"Ya existe un proyecto llamado «{nombre}».",
                                "Use otro nombre o abra el existente.")
        return self.repo.crear_proyecto(nombre, tipo_tarea, descripcion)

    def listar_proyectos(self) -> list[dict]:
        return self.repo.listar_proyectos()

    def proyecto(self, proyecto_id: int) -> dict:
        p = self.repo.obtener_proyecto(proyecto_id)
        if not p:
            raise ErrorServicio("El proyecto no existe.", "Elija otro proyecto de la lista.")
        return p

    def estado(self, proyecto_id: int) -> dict:
        e = self.proyecto(proyecto_id).get("estado_pipeline") or {}
        e.setdefault("paso_actual", "importacion")
        e.setdefault("completados", ["proyecto"])
        return e

    def marcar_paso(self, proyecto_id: int, completado: str, siguiente: str | None = None,
                    **extra) -> dict:
        e = self.estado(proyecto_id)
        if completado not in e["completados"]:
            e["completados"].append(completado)
        if siguiente:
            e["paso_actual"] = siguiente
        e.update(extra)
        self.repo.guardar_estado_pipeline(proyecto_id, e)
        return e

    def ir_a_paso(self, proyecto_id: int, paso: str) -> None:
        e = self.estado(proyecto_id)
        e["paso_actual"] = paso
        self.repo.guardar_estado_pipeline(proyecto_id, e)

    def _carpeta_datasets(self, proyecto_id: int) -> Path:
        return self.almacen.datasets / f"p{proyecto_id}"

    # --- importación -------------------------------------------------------------------
    def importar(self, ctx: Contexto, proyecto_id: int, rutas: list,
                 opciones: importador.OpcionesImportacion) -> dict:
        self.proyecto(proyecto_id)
        resumen = importador.importar_lote(rutas, opciones, ctx)
        self._lotes[proyecto_id] = resumen
        compatible, diferencias = importador.comparar_esquemas(resumen.resultados)
        return {"resumen": resumen, "compatible": compatible, "diferencias": diferencias}

    def reimportar_fichero(self, proyecto_id: int, ruta: str,
                           opciones: importador.OpcionesImportacion) -> importador.ResultadoFichero:
        res = importador.importar_fichero(ruta, opciones)
        lote = self._lotes.setdefault(proyecto_id, importador.ResumenLote())
        lote.resultados = [res if r.ruta == ruta else r for r in lote.resultados]
        if all(r.ruta != ruta for r in lote.resultados):
            lote.resultados.append(res)
        return res

    def lote_actual(self, proyecto_id: int) -> importador.ResumenLote | None:
        return self._lotes.get(proyecto_id)

    def comparar_lote(self, proyecto_id: int) -> tuple[bool, dict]:
        lote = self._lotes.get(proyecto_id)
        if not lote:
            return True, {}
        return importador.comparar_esquemas(lote.resultados)

    def confirmar_importacion(self, proyecto_id: int, estrategia: str = "compatible") -> dict:
        """Combina el lote, guarda el dataset bruto y registra la procedencia."""
        lote = self._lotes.get(proyecto_id)
        if not lote or not lote.validos:
            raise ErrorServicio("No hay ningún fichero importado válido.",
                                "Importe al menos un fichero sin errores bloqueantes.")
        try:
            df = importador.combinar(lote.resultados, estrategia)
        except importador.ErrorImportacion as e:
            raise ErrorServicio(str(e), "Elija unión o intersección de columnas.") from e
        for r in lote.resultados:
            self.repo.registrar_fichero(
                proyecto_id, r.ruta, r.nombre, r.formato, r.tamano, r.filas, r.columnas, r.hash,
                r.codificacion, r.delimitador, r.hoja, r.estado,
                r.avisos + ([r.error] if r.error else []))
        carpeta = self._carpeta_datasets(proyecto_id)
        ruta = carpeta / f"bruto_{datetime.now():%Y%m%d_%H%M%S}.csv"
        importador.guardar_csv_canonico(df, ruta)
        h = importador.hash_dataframe(df)
        dataset_id = self.repo.crear_dataset(
            proyecto_id, "bruto", ruta.stem, str(ruta), len(df), df.shape[1], h,
            preparacion={"estrategia_combinacion": estrategia,
                         "ficheros": [r.nombre for r in lote.validos]})
        self._brutos[proyecto_id] = df
        self.marcar_paso(proyecto_id, "importacion", "dataset", dataset_bruto_id=dataset_id)
        return {"dataset_id": dataset_id, "filas": len(df), "columnas": df.shape[1], "hash": h,
                "validacion": importador.resumen_columnas(df)}

    def dataset_bruto(self, proyecto_id: int) -> dict | None:
        return self.repo.ultimo_dataset(proyecto_id, "bruto")

    def datos_brutos(self, proyecto_id: int) -> pd.DataFrame | None:
        if proyecto_id in self._brutos:
            return self._brutos[proyecto_id]
        ds = self.repo.ultimo_dataset(proyecto_id, "bruto")
        if not ds or not Path(ds["ruta"]).exists():
            return None
        df = importador.leer_csv_canonico(ds["ruta"])
        self._brutos[proyecto_id] = df
        return df

    def columnas_brutas(self, proyecto_id: int) -> list[str]:
        df = self.datos_brutos(proyecto_id)
        return [] if df is None else list(df.columns)

    def validacion_bruta(self, proyecto_id: int) -> list[dict]:
        df = self.datos_brutos(proyecto_id)
        return [] if df is None else importador.resumen_columnas(df)

    # --- preparación y línea base ----------------------------------------------------------
    def preparar(self, ctx: Contexto, proyecto_id: int,
                 config: preparador.ConfigPreparacion) -> dict:
        p = self.proyecto(proyecto_id)
        df = self.datos_brutos(proyecto_id)
        if df is None:
            raise ErrorServicio("No hay datos importados en este proyecto.",
                                "Vuelva al paso 2 e importe los ficheros.")
        ctx.log("Limpiando y dividiendo el dataset…")
        ctx.progreso(10)
        try:
            res = preparador.preparar(df, p["tipo_tarea"], config)
        except preparador.ErrorPreparacion as e:
            raise ErrorServicio(str(e), "Corrija la configuración del paso 3 y vuelva a preparar.") from e
        for a in res.avisos:
            ctx.log(f"aviso: {a}")
        ctx.progreso(50)
        bruto = self.repo.ultimo_dataset(proyecto_id, "bruto")
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        carpeta = self._carpeta_datasets(proyecto_id) / f"preparado_{sello}"
        rutas = {}
        for nombre, parte in (("train", res.train), ("val", res.val), ("test", res.test)):
            rutas[nombre] = str(carpeta / f"{nombre}.csv")
            importador.guardar_csv_canonico(parte, rutas[nombre])
        completo = pd.concat([res.train, res.val, res.test], ignore_index=True)
        h = importador.hash_dataframe(completo)
        dataset_id = self.repo.crear_dataset(
            proyecto_id, "preparado", carpeta.name, str(carpeta), len(completo),
            completo.shape[1], h, config.objetivo, res.division,
            {"config": config.como_dict(), "especificacion": res.especificacion,
             "avisos": res.avisos, "rutas": rutas, "bruto_id": bruto["id"] if bruto else None,
             "hash_bruto": bruto["hash"] if bruto else None})
        ctx.log("Calculando la línea base…")
        base = evaluador.calcular_linea_base(res.train, res.test, config.objetivo, p["tipo_tarea"])
        self.repo.guardar_metricas(proyecto_id, base, "baseline", "test", dataset_id=dataset_id)
        ctx.progreso(100)
        self.marcar_paso(proyecto_id, "dataset", "entrenamiento", dataset_id=dataset_id)
        ctx.log(f"Dataset preparado: {res.division['filas']} · hash {h[:12]}…")
        return {"dataset_id": dataset_id, "division": res.division, "linea_base": base,
                "avisos": res.avisos, "especificacion": res.especificacion, "hash": h}

    def linea_base(self, proyecto_id: int) -> dict:
        ds = self.repo.ultimo_dataset(proyecto_id, "preparado")
        if not ds:
            return {}
        return self.repo.obtener_metricas("baseline", dataset_id=ds["id"])

    def dataset_preparado(self, proyecto_id: int) -> dict | None:
        return self.repo.ultimo_dataset(proyecto_id, "preparado")

    # --- configuración y entrenamiento ---------------------------------------------------------
    @staticmethod
    def hiperparametros_iniciales(tipo_tarea: str, framework: str) -> dict:
        if framework == "sklearn":
            return dict(INICIALES[tipo_tarea])
        return dict(INICIALES_RED)

    @staticmethod
    def metricas_objetivo(tipo_tarea: str) -> list[str]:
        return METRICAS_OBJETIVO[tipo_tarea]

    @staticmethod
    def umbrales_por_defecto(tipo_tarea: str) -> dict:
        return evaluador.umbrales_por_defecto(tipo_tarea)

    def guardar_configuracion(self, proyecto_id: int, framework: str, hiperparametros: dict,
                              umbrales: dict, metrica_objetivo: str, max_reintentos: int,
                              semilla: int) -> int:
        if framework not in entrenador.FRAMEWORKS:
            raise ErrorServicio(f"Framework «{framework}» desconocido.", "Elija uno de la lista.")
        if not isinstance(hiperparametros, dict):
            raise ErrorServicio("Los hiperparámetros deben ser un objeto JSON.",
                                "Corrija el JSON de hiperparámetros.")
        return self.repo.crear_configuracion(
            proyecto_id, framework, entrenador.FRAMEWORKS[framework]["script"], hiperparametros,
            umbrales, metrica_objetivo, int(max_reintentos), int(semilla))

    def entrenar(self, ctx: Contexto, proyecto_id: int, configuracion_id: int,
                 ejecutor=None) -> dict:
        """Entrena, evalúa y reintenta según la política. Cada intento es una fila nueva."""
        p = self.proyecto(proyecto_id)
        tipo = p["tipo_tarea"]
        ds = self.repo.ultimo_dataset(proyecto_id, "preparado")
        if not ds:
            raise ErrorServicio("No hay dataset preparado.", "Prepare el dataset en el paso 3.")
        base = self.repo.obtener_metricas("baseline", dataset_id=ds["id"])
        if not base:
            raise ErrorServicio("Falta la línea base del dataset.",
                                "Vuelva a preparar el dataset en el paso 3.")
        cfg = self.repo.obtener_configuracion(configuracion_id)
        especificacion = ds["preparacion"]["especificacion"]
        rutas = ds["preparacion"]["rutas"]
        script = carpeta_scripts() / cfg["script"]
        if not script.exists():
            raise ErrorServicio(f"No se encuentra el script {cfg['script']}.",
                                "Reinstale la aplicación.")
        from infra.ejecutor_ssh import ErrorEjecutor
        ejecutor = ejecutor or self.crear_ejecutor()
        try:
            ejecutor.comprobar_conexion()
        except ErrorEjecutor as e:
            ejecutor.cerrar()
            raise self._error_conexion(ejecutor, e) from e
        historial: list[dict] = []
        hp = dict(cfg["hiperparametros"])
        intento, padre, motivo = 0, None, "inicial"
        mejor = None
        try:
            while True:
                ctx.comprobar()
                ej_id = self.repo.crear_ejecucion(proyecto_id, configuracion_id, ds["id"],
                                                  intento, padre, motivo, ejecutor.modo, hp)
                ctx.log(f"── Ejecución #{ej_id} · intento {intento} · {motivo}")
                ctx.evento({"evento": "ejecucion", "id": ej_id, "intento": intento})
                carpeta = self.almacen.modelos / f"p{proyecto_id}_{_slug(p['nombre'])}" / f"e{ej_id}"
                config = entrenador.construir_config(tipo, especificacion, hp, cfg["semilla"],
                                                     cfg["metrica_objetivo"])
                entrenador.preparar_carpeta_trabajo(carpeta, config, rutas, script)
                ctx.progreso(0)
                try:
                    r = entrenador.lanzar(ejecutor, carpeta, script.name, ctx)
                except Exception as e:  # noqa: BLE001 - fallo técnico del ejecutor
                    if isinstance(e, Cancelado):
                        raise
                    log.exception("Fallo al lanzar la ejecución %s", ej_id)
                    r = entrenador.ResultadoEntrenamiento(
                        estado="error", metricas={}, ruta_modelo=None, duracion_s=0.0,
                        hiperparametros=hp, versiones={}, error=str(e), codigo_salida=-1,
                        comando="", carpeta=carpeta,
                        log=[(datetime.now().isoformat(timespec="seconds"), str(e))])
                ruta_log = self.almacen.logs / f"ejecucion_{ej_id}.log"
                if (carpeta / "ejecucion.log").exists():
                    shutil.copyfile(carpeta / "ejecucion.log", ruta_log)
                else:
                    ruta_log.write_text(r.texto_log, encoding="utf-8")
                self.repo.anadir_logs(proyecto_id, ej_id, [(m, "INFO", t) for m, t in r.log])
                datos_ej = {"estado": r.estado, "log": r.texto_log, "error": r.error,
                            "hiperparametros": hp, "motivo": motivo, "intento": intento}
                ver = {"veredicto": "error", "motivos": [r.error or "Fallo técnico."],
                       "comprobaciones": []}
                metricas = {}
                if r.estado == "ok":
                    pred = carpeta / "predicciones_test.csv"
                    metricas = (evaluador.metricas_desde_predicciones(tipo, pred)
                                if pred.exists() else dict(r.metricas))
                    self.repo.guardar_metricas(proyecto_id, metricas, "modelo", "test",
                                               dataset_id=ds["id"], ejecucion_id=ej_id)
                    ver = evaluador.veredicto(tipo, metricas, base, cfg["umbrales"],
                                              cfg["metrica_objetivo"])
                datos_ej["veredicto"] = ver["veredicto"]
                self.repo.actualizar_ejecucion(
                    ej_id, estado=("cancelada" if ctx.cancelado() else r.estado),
                    comando=r.comando, versiones_json=r.versiones, curva_json=r.curva,
                    ruta_modelo=str(carpeta / r.ruta_modelo) if r.ruta_modelo else None,
                    ruta_log=str(ruta_log), duracion_s=r.duracion_s, veredicto=ver["veredicto"],
                    detalle_veredicto_json=ver, error=r.error,
                    terminada=datetime.now().isoformat(timespec="seconds"))
                ctx.log(f"Veredicto #{ej_id}: {ver['veredicto']}"
                        + (f" · {'; '.join(ver['motivos'])}" if ver["motivos"] else ""))
                ctx.evento({"evento": "fin_ejecucion", "id": ej_id, "veredicto": ver["veredicto"]})
                historial.append(datos_ej)
                if r.estado == "ok":
                    nombre = evaluador.metrica_principal(tipo, cfg["metrica_objetivo"])
                    if mejor is None or (metricas.get(nombre) or -1e9) > (mejor[1] or -1e9):
                        mejor = (ej_id, metricas.get(nombre))
                ctx.comprobar()
                decision = reintentos.decidir(tipo, datos_ej, historial, cfg["max_reintentos"])
                ctx.log(f"Reintentos: {decision.explicacion}")
                if not decision.reintentar:
                    break
                intento, padre, motivo = intento + 1, ej_id, decision.motivo
                hp = decision.hiperparametros or hp
        finally:
            ejecutor.cerrar()
        self.marcar_paso(proyecto_id, "entrenamiento", "resultados")
        return {"ejecuciones": len(historial), "mejor_id": mejor[0] if mejor else None,
                "veredicto": historial[-1]["veredicto"] if historial else None}

    def ejecuciones(self, proyecto_id: int) -> list[dict]:
        return self.repo.listar_ejecuciones(proyecto_id)

    def ultima_configuracion(self, proyecto_id: int) -> dict | None:
        return self.repo.ultima_configuracion(proyecto_id)

    # --- resultados ---------------------------------------------------------------------------
    def resumen_resultados(self, proyecto_id: int) -> dict:
        p = self.proyecto(proyecto_id)
        tipo = p["tipo_tarea"]
        cfg = self.repo.ultima_configuracion(proyecto_id) or {}
        metrica_objetivo = cfg.get("metrica_objetivo")
        nombre = evaluador.metrica_principal(tipo, metrica_objetivo)
        ds = self.repo.ultimo_dataset(proyecto_id, "preparado")
        base = self.repo.obtener_metricas("baseline", dataset_id=ds["id"]) if ds else {}
        filas, mejor, mejor_m = [], None, None
        for e in self.repo.listar_ejecuciones(proyecto_id):
            m = self.repo.obtener_metricas("modelo", ejecucion_id=e["id"]) if e["estado"] == "ok" else {}
            fila = {**e, "metricas": m, "metrica": m.get(nombre)}
            filas.append(fila)
            if m.get(nombre) is not None and (mejor is None or m[nombre] > mejor["metrica"]):
                mejor, mejor_m = fila, m
        cadena = [f for f in filas if mejor and f["configuracion_id"] == mejor["configuracion_id"]]
        kpis = {
            "metrica_nombre": nombre,
            "metrica_valor": mejor["metrica"] if mejor else None,
            "mejora": (evaluador.mejora_sobre_base(tipo, mejor_m, base, metrica_objetivo)
                       if mejor else None),
            "duracion_s": sum(f["duracion_s"] or 0 for f in cadena) if cadena else None,
            "reintentos": sum(1 for f in cadena if f["intento"] > 0) if cadena else None,
            "veredicto": mejor["veredicto"] if mejor else None,
        }
        ruta_pred = None
        if mejor and mejor.get("ruta_modelo"):
            ruta_pred = str(Path(mejor["ruta_modelo"]).parent / "predicciones_test.csv")
        return {"proyecto": p, "kpis": kpis, "ejecuciones": filas, "mejor": mejor,
                "metricas_mejor": mejor_m or {}, "linea_base": base, "dataset": ds,
                "configuracion": cfg, "ruta_predicciones": ruta_pred}

    # --- informe ------------------------------------------------------------------------------
    def datos_informe(self, proyecto_id: int) -> dict:
        r = self.resumen_resultados(proyecto_id)
        ds = r["dataset"] or {}
        ficheros = self.repo.listar_ficheros(proyecto_id)
        mejor = r["mejor"] or {}
        cfg_mejor = (self.repo.obtener_configuracion(mejor["configuracion_id"])
                     if mejor.get("configuracion_id") else r["configuracion"]) or {}
        prep = ds.get("preparacion") or {}
        return {
            "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "proyecto": {k: r["proyecto"].get(k) for k in
                         ("nombre", "tipo_tarea", "descripcion", "creado")},
            "kpis": r["kpis"], "linea_base": r["linea_base"], "mejor": mejor or None,
            "metricas_mejor": r["metricas_mejor"], "ruta_predicciones": r["ruta_predicciones"],
            "dataset": {"filas": ds.get("filas"), "columnas": ds.get("columnas"),
                        "hash": ds.get("hash"), "objetivo": ds.get("objetivo"),
                        "division": ds.get("division"),
                        "especificacion": prep.get("especificacion")},
            "ficheros": ficheros,
            "configuracion": {"framework": cfg_mejor.get("framework"),
                              "script": cfg_mejor.get("script"),
                              "hiperparametros": mejor.get("hiperparametros") or
                              cfg_mejor.get("hiperparametros"),
                              "umbrales": cfg_mejor.get("umbrales"),
                              "metrica_objetivo": cfg_mejor.get("metrica_objetivo"),
                              "max_reintentos": cfg_mejor.get("max_reintentos"),
                              "semilla": cfg_mejor.get("semilla")},
            "ejecuciones": [{k: e.get(k) for k in ("id", "intento", "motivo", "estado",
                                                   "veredicto", "metrica", "duracion_s", "error")}
                            for e in r["ejecuciones"]],
            "trazabilidad": {"semilla": cfg_mejor.get("semilla"), "hash_dataset": ds.get("hash"),
                             "hash_bruto": prep.get("hash_bruto"),
                             "hashes_ficheros": {f["nombre"]: f["hash"] for f in ficheros},
                             "versiones": mejor.get("versiones"), "comando": mejor.get("comando"),
                             "modo": mejor.get("modo"), "ruta_log": mejor.get("ruta_log"),
                             "ruta_modelo": mejor.get("ruta_modelo")},
        }

    def exportar_informe(self, ctx: Contexto, proyecto_id: int) -> dict:
        p = self.proyecto(proyecto_id)
        ctx.log("Reuniendo resultados…")
        ctx.progreso(10)
        datos = self.datos_informe(proyecto_id)
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        carpeta = self.almacen.informes / f"p{proyecto_id}_{_slug(p['nombre'])}" / sello
        ctx.log("Generando gráficas, Word y PDF…")
        ctx.progreso(40)
        docx, pdf = exportador.exportar_informe(datos, carpeta, f"informe_{_slug(p['nombre'])}")
        ctx.progreso(90)
        self.repo.registrar_informe(proyecto_id, str(docx), str(pdf),
                                    importador.hash_fichero(docx), importador.hash_fichero(pdf))
        self.marcar_paso(proyecto_id, "resultados")
        self.marcar_paso(proyecto_id, "informe", "informe")
        ctx.progreso(100)
        ctx.log(f"Informe: {docx}")
        return {"docx": str(docx), "pdf": str(pdf)}

    def informes(self, proyecto_id: int) -> list[dict]:
        return self.repo.listar_informes(proyecto_id)

