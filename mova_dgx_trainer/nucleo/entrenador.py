"""Entrenador: configuración, lanzamiento en la DGX (o en local) y captura de logs.

Invocación: python <script> --config config.json --salida resultado.json, a
través de `infra.ejecutor_ssh` (misma interfaz en local y en remoto).
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nucleo.contexto import Contexto

FRAMEWORKS = {
    "sklearn": {"script": "entrenar_sklearn.py", "etiqueta": "scikit-learn",
                "verificado": True},
    "torch": {"script": "entrenar_torch.py",
              "etiqueta": "PyTorch [PENDIENTE: no verificado]", "verificado": False},
    "tensorflow": {"script": "entrenar_tensorflow.py",
                   "etiqueta": "TensorFlow [PENDIENTE: no verificado]", "verificado": False},
}

CLAVES_RESULTADO = ("estado", "metricas", "ruta_modelo", "duracion_s", "hiperparametros",
                    "versiones", "error")


@dataclass
class ResultadoEntrenamiento:
    estado: str
    metricas: dict
    ruta_modelo: str | None
    duracion_s: float
    hiperparametros: dict
    versiones: dict
    error: str | None
    codigo_salida: int
    comando: str
    carpeta: Path
    log: list = field(default_factory=list)       # [(momento, texto)]
    curva: list = field(default_factory=list)     # eventos de progreso

    @property
    def texto_log(self) -> str:
        return "\n".join(t for _, t in self.log)


def parsear_linea(linea: str) -> dict:
    """Una línea de stdout → evento. Lo no parseable se trata como log."""
    texto = linea.strip()
    if texto.startswith("{"):
        try:
            datos = json.loads(texto)
        except ValueError:
            return {"evento": "log", "texto": linea}
        if isinstance(datos, dict) and datos.get("evento") in ("progreso", "log"):
            if datos["evento"] == "log":
                datos["texto"] = str(datos.get("texto", ""))
            return datos
    return {"evento": "log", "texto": linea}


def construir_config(tipo_tarea: str, especificacion: dict, hiperparametros: dict,
                     semilla: int, metrica_objetivo: str) -> dict:
    return {
        "tipo_tarea": tipo_tarea,
        "especificacion": especificacion,
        "hiperparametros": hiperparametros,
        "semilla": int(semilla),
        "metrica_objetivo": metrica_objetivo,
        "ficheros": {"train": "train.csv", "val": "val.csv", "test": "test.csv"},
    }


def preparar_carpeta_trabajo(carpeta: Path, config: dict, rutas_division: dict,
                             script: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, ruta in rutas_division.items():
        shutil.copyfile(ruta, carpeta / f"{nombre}.csv")
    shutil.copyfile(script, carpeta / script.name)
    (carpeta / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2),
                                         encoding="utf-8")


def normalizar_resultado(datos: dict | None, codigo: int, error_extra: str = "") -> dict:
    datos = dict(datos or {})
    r = {k: datos.get(k) for k in CLAVES_RESULTADO}
    r["metricas"] = r["metricas"] or {}
    r["hiperparametros"] = r["hiperparametros"] or {}
    r["versiones"] = r["versiones"] or {}
    r["duracion_s"] = float(r["duracion_s"] or 0.0)
    if r["estado"] not in ("ok", "error"):
        r["estado"] = "error"
        r["error"] = r["error"] or error_extra or "El script no escribió un resultado válido."
    if r["estado"] == "ok" and codigo != 0:
        r["estado"] = "error"
        r["error"] = f"El script terminó con código {codigo} aunque declaró estado ok."
    return r


def lanzar(ejecutor, carpeta: Path, script_nombre: str, ctx: Contexto) -> ResultadoEntrenamiento:
    """Ejecuta el script en la carpeta de trabajo (subida y bajada si es remoto)."""
    ctx.log(f"Modo de ejecución: {ejecutor.describir()}")
    nombre_trabajo = f"{carpeta.parent.name}_{carpeta.name}"
    carpeta_ejec = ejecutor.preparar_carpeta(carpeta, nombre_trabajo)
    comando = [ejecutor.interprete, script_nombre, "--config", "config.json",
               "--salida", "resultado.json"]
    comando_txt = " ".join(comando)
    ctx.log(f"Comando: {comando_txt}  (cwd {carpeta_ejec})")
    log: list = []
    curva: list = []

    def al_recibir(linea: str) -> None:
        momento = datetime.now().isoformat(timespec="seconds")
        evento = parsear_linea(linea)
        if evento["evento"] == "progreso":
            curva.append(evento)
            log.append((momento, json.dumps(evento, ensure_ascii=False)))
            total = evento.get("total") or 1
            ctx.progreso(100 * float(evento.get("epoca", 0)) / float(total))
            ctx.evento(evento)
        else:
            log.append((momento, evento["texto"]))
            ctx.log(evento["texto"])

    inicio = time.time()
    codigo = ejecutor.ejecutar(comando, carpeta_ejec, al_recibir, ctx.cancelado)
    if ctx.cancelado():
        datos, extra = {"estado": "error", "error": "Cancelado por el usuario."}, ""
    else:
        if ejecutor.modo == "remoto":
            ctx.log("Bajando artefactos de la DGX Spark…")
            ejecutor.recuperar(carpeta_ejec, carpeta)
        ruta = carpeta / "resultado.json"
        extra = ""
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            datos, extra = None, f"No se pudo leer resultado.json ({e})."
    r = normalizar_resultado(datos, codigo, extra)
    if not r["duracion_s"]:
        r["duracion_s"] = round(time.time() - inicio, 3)
    (carpeta / "ejecucion.log").write_text(
        "\n".join(f"{m} {t}" for m, t in log), encoding="utf-8")
    return ResultadoEntrenamiento(codigo_salida=codigo, comando=comando_txt, carpeta=carpeta,
                                  log=log, curva=curva, **r)
