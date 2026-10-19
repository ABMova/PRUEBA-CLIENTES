"""Política de reintentos.

- Fallo técnico con error de memoria CUDA en el log: batch_size a la mitad.
- Otro fallo técnico: un único reintento con la misma configuración.
- Desempeño insuficiente: siguiente combinación de la rejilla del tipo de tarea.
- Máximo configurable (3 por defecto); 0 desactiva los reintentos.
Cada reintento es una ejecución nueva: nunca se sobrescribe la anterior.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from nucleo.rejillas import siguiente_de_rejilla

MAX_REINTENTOS_POR_DEFECTO = 3
BATCH_POR_DEFECTO = 64

PATRON_OOM_CUDA = re.compile(
    r"CUDA out of memory|CUDA error: out of memory|torch\.(cuda\.)?OutOfMemoryError|"
    r"OutOfMemoryError: CUDA|CUDA_ERROR_OUT_OF_MEMORY|cudaErrorMemoryAllocation|"
    r"RESOURCE_EXHAUSTED.*(OOM|out of memory)|failed to allocate .* on device|"
    r"CUBLAS_STATUS_ALLOC_FAILED", re.IGNORECASE)

MOTIVO_OOM = "oom_cuda"
MOTIVO_TECNICO = "fallo_tecnico"
MOTIVO_DESEMPENO = "desempeno"


@dataclass
class Decision:
    reintentar: bool
    motivo: str
    explicacion: str
    hiperparametros: dict | None = None


def es_error_memoria_cuda(texto: str) -> bool:
    return bool(texto) and PATRON_OOM_CUDA.search(texto) is not None


def decidir(tipo_tarea: str, ejecucion: dict, historial: list[dict],
            max_reintentos: int = MAX_REINTENTOS_POR_DEFECTO) -> Decision:
    """Decide el siguiente paso tras una ejecución.

    ejecucion: {estado: ok|error, veredicto, log, error, hiperparametros, motivo}
    historial: ejecuciones anteriores de la misma cadena (incluida esta), cada
               una con {intento, motivo, hiperparametros}.
    """
    reintentos_hechos = sum(1 for e in historial if int(e.get("intento", 0)) > 0)
    if max_reintentos <= 0:
        return Decision(False, "desactivados", "Los reintentos están desactivados.")
    if reintentos_hechos >= max_reintentos:
        return Decision(False, "maximo", f"Alcanzado el máximo de {max_reintentos} reintentos.")

    hp = dict(ejecucion.get("hiperparametros") or {})
    if ejecucion.get("estado") != "ok":
        texto = f"{ejecucion.get('log', '')}\n{ejecucion.get('error', '')}"
        if es_error_memoria_cuda(texto):
            actual = int(hp.get("batch_size") or BATCH_POR_DEFECTO)
            if actual <= 1:
                return Decision(False, MOTIVO_OOM, "Error de memoria CUDA con batch_size 1: "
                                "no se puede reducir más.")
            hp["batch_size"] = max(1, actual // 2)
            return Decision(True, MOTIVO_OOM,
                            f"Error de memoria CUDA: batch_size {actual} → {hp['batch_size']}.", hp)
        if ejecucion.get("motivo") == MOTIVO_TECNICO:
            return Decision(False, MOTIVO_TECNICO, "El reintento con la misma configuración "
                            "también ha fallado.")
        return Decision(True, MOTIVO_TECNICO, "Fallo técnico: un reintento con la misma "
                        "configuración.", hp)

    if ejecucion.get("veredicto") == "aprobado":
        return Decision(False, "aprobado", "La ejecución cumple los umbrales.")

    probados = [e.get("hiperparametros") or {} for e in historial]
    siguiente = siguiente_de_rejilla(tipo_tarea, probados)
    if siguiente is None:
        return Decision(False, MOTIVO_DESEMPENO, "Rejilla agotada sin alcanzar los umbrales.")
    if "batch_size" in hp:
        siguiente.setdefault("batch_size", hp["batch_size"])
    return Decision(True, MOTIVO_DESEMPENO, "Desempeño insuficiente: siguiente combinación "
                    f"de la rejilla ({siguiente.get('modelo', '?')}).", siguiente)
