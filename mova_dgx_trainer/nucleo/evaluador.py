"""Evaluador: métricas sobre test, línea base y veredicto.

Las métricas del modelo se recalculan aquí a partir de las predicciones que
escribe el script (`predicciones_test.csv`), con las mismas funciones que la
línea base: así ambas son comparables.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score, recall_score,
                             roc_auc_score)

from nucleo.rejillas import es_clasificacion

UMBRALES_POR_DEFECTO = {
    "clasificacion": {"minimo": 0.70, "margen_baseline": 0.10},
    "regresion": {"r2_minimo": 0.50, "factor_mae": 0.90},
}


def umbrales_por_defecto(tipo_tarea: str) -> dict:
    return dict(UMBRALES_POR_DEFECTO["clasificacion" if es_clasificacion(tipo_tarea)
                                     else "regresion"])


def _r(x: float) -> float:
    return float(round(float(x), 6))


def metricas_clasificacion(y_real, y_pred, prob_positiva=None) -> dict:
    y_real = pd.Series(y_real).astype(str).to_numpy()
    y_pred = pd.Series(y_pred).astype(str).to_numpy()
    etiquetas = sorted(set(y_real) | set(y_pred))
    m = {
        "accuracy": _r(accuracy_score(y_real, y_pred)),
        "precision_macro": _r(precision_score(y_real, y_pred, average="macro", zero_division=0)),
        "recall_macro": _r(recall_score(y_real, y_pred, average="macro", zero_division=0)),
        "f1_macro": _r(f1_score(y_real, y_pred, average="macro", zero_division=0)),
        "precision_ponderado": _r(precision_score(y_real, y_pred, average="weighted",
                                                  zero_division=0)),
        "recall_ponderado": _r(recall_score(y_real, y_pred, average="weighted", zero_division=0)),
        "f1_ponderado": _r(f1_score(y_real, y_pred, average="weighted", zero_division=0)),
        "matriz_confusion": {"etiquetas": etiquetas,
                             "valores": confusion_matrix(y_real, y_pred, labels=etiquetas).tolist()},
    }
    clases_reales = sorted(set(y_real))
    if len(clases_reales) == 2 and prob_positiva is not None:
        p = pd.to_numeric(pd.Series(prob_positiva), errors="coerce")
        if p.notna().all():
            positiva = clases_reales[1]
            try:
                m["roc_auc"] = _r(roc_auc_score((y_real == positiva).astype(int), p))
            except ValueError:
                pass
    return m


def metricas_regresion(y_real, y_pred) -> dict:
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {"mae": _r(mean_absolute_error(y_real, y_pred)),
            "rmse": _r(math.sqrt(mean_squared_error(y_real, y_pred))),
            "r2": _r(r2_score(y_real, y_pred))}


def calcular_metricas(tipo_tarea: str, y_real, y_pred, prob_positiva=None) -> dict:
    if es_clasificacion(tipo_tarea):
        return metricas_clasificacion(y_real, y_pred, prob_positiva)
    return metricas_regresion(y_real, y_pred)


def calcular_linea_base(train: pd.DataFrame, test: pd.DataFrame, objetivo: str,
                        tipo_tarea: str) -> dict:
    """DummyClassifier(most_frequent) o DummyRegressor(mean) sobre el mismo split."""
    x_tr = np.zeros((len(train), 1))
    x_te = np.zeros((len(test), 1))
    if es_clasificacion(tipo_tarea):
        modelo = DummyClassifier(strategy="most_frequent")
        modelo.fit(x_tr, train[objetivo].astype(str))
        pred = modelo.predict(x_te)
        prob = None
        if len(modelo.classes_) == 2:
            prob = modelo.predict_proba(x_te)[:, 1]
        m = metricas_clasificacion(test[objetivo].astype(str), pred, prob)
        m["estrategia"] = "most_frequent"
    else:
        modelo = DummyRegressor(strategy="mean")
        modelo.fit(x_tr, train[objetivo].astype(float))
        m = metricas_regresion(test[objetivo].astype(float), modelo.predict(x_te))
        m["estrategia"] = "mean"
    return m


def metricas_desde_predicciones(tipo_tarea: str, ruta_csv) -> dict:
    pred = pd.read_csv(ruta_csv, encoding="utf-8")
    prob = pred["prob_positiva"] if "prob_positiva" in pred.columns else None
    if es_clasificacion(tipo_tarea):
        return metricas_clasificacion(pred["y_real"].astype(str), pred["y_pred"].astype(str), prob)
    return metricas_regresion(pred["y_real"], pred["y_pred"])


def metrica_principal(tipo_tarea: str, metrica_objetivo: str | None = None) -> str:
    if es_clasificacion(tipo_tarea):
        return metrica_objetivo or "f1_macro"
    return "r2"


def veredicto(tipo_tarea: str, metricas: dict, base: dict, umbrales: dict | None = None,
              metrica_objetivo: str | None = None) -> dict:
    """Devuelve {veredicto: aprobado|insuficiente, motivos, comprobaciones}."""
    u = {**umbrales_por_defecto(tipo_tarea), **(umbrales or {})}
    comprobaciones = []
    if es_clasificacion(tipo_tarea):
        nombre = metrica_principal(tipo_tarea, metrica_objetivo)
        valor, valor_base = metricas.get(nombre), base.get(nombre)
        if valor is None or valor_base is None:
            return {"veredicto": "insuficiente", "comprobaciones": [],
                    "motivos": [f"[PENDIENTE: métrica {nombre}] no disponible."]}
        comprobaciones.append({"regla": f"{nombre} ≥ {u['minimo']:.2f}",
                               "valor": valor, "cumple": valor >= u["minimo"]})
        limite = valor_base + u["margen_baseline"]
        comprobaciones.append({"regla": f"{nombre} ≥ baseline + {u['margen_baseline']:.2f} "
                                        f"({limite:.4f})",
                               "valor": valor, "cumple": valor >= limite - 1e-12})
    else:
        r2, mae, mae_base = metricas.get("r2"), metricas.get("mae"), base.get("mae")
        if r2 is None or mae is None or mae_base is None:
            return {"veredicto": "insuficiente", "comprobaciones": [],
                    "motivos": ["[PENDIENTE: métricas de regresión] no disponibles."]}
        comprobaciones.append({"regla": f"r2 ≥ {u['r2_minimo']:.2f}", "valor": r2,
                               "cumple": r2 >= u["r2_minimo"]})
        limite = u["factor_mae"] * mae_base
        comprobaciones.append({"regla": f"mae ≤ {u['factor_mae']:.2f} × baseline.mae "
                                        f"({limite:.4f})",
                               "valor": mae, "cumple": mae <= limite + 1e-12})
    ok = all(c["cumple"] for c in comprobaciones)
    motivos = [f"No cumple: {c['regla']} (valor {c['valor']:.4f})"
               for c in comprobaciones if not c["cumple"]]
    return {"veredicto": "aprobado" if ok else "insuficiente", "motivos": motivos,
            "comprobaciones": comprobaciones}


def mejora_sobre_base(tipo_tarea: str, metricas: dict, base: dict,
                      metrica_objetivo: str | None = None) -> float | None:
    nombre = metrica_principal(tipo_tarea, metrica_objetivo)
    if metricas.get(nombre) is None or base.get(nombre) is None:
        return None
    return float(metricas[nombre]) - float(base[nombre])
