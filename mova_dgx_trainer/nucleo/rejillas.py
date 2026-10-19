"""Hiperparámetros iniciales y rejillas de reintento por tipo de tarea.

Las rejillas se recorren en orden cuando una ejecución termina con desempeño
insuficiente. Son para `entrenar_sklearn.py`; los scripts de PyTorch y
TensorFlow usan `INICIALES_RED` [PENDIENTE: no verificados].
"""
from __future__ import annotations

TIPOS_TAREA = {
    "clasificacion_tabular": "Clasificación tabular",
    "regresion_tabular": "Regresión tabular",
    "clasificacion_texto": "Clasificación de texto",
}
TIPO_PENDIENTE = ("ajuste_fino_llm", "Ajuste fino de LLM [PENDIENTE: confirmar alcance]")

INICIALES = {
    "clasificacion_tabular": {"modelo": "random_forest", "n_estimators": 200,
                              "max_depth": None, "min_samples_leaf": 1, "etapas": 5},
    "regresion_tabular": {"modelo": "random_forest", "n_estimators": 200,
                          "max_depth": None, "min_samples_leaf": 1, "etapas": 5},
    "clasificacion_texto": {"modelo": "tfidf_logistica", "C": 1.0, "max_features": 20000,
                            "ngram_max": 2},
}

INICIALES_RED = {"epocas": 20, "batch_size": 64, "tasa_aprendizaje": 0.001,
                 "capas_ocultas": [128, 64], "dropout": 0.1}

REJILLAS = {
    "clasificacion_tabular": [
        {"modelo": "hist_gradient_boosting", "learning_rate": 0.1, "max_iter": 200,
         "max_leaf_nodes": 31, "etapas": 5},
        {"modelo": "random_forest", "n_estimators": 400, "max_depth": None,
         "min_samples_leaf": 2, "class_weight": "balanced", "etapas": 5},
        {"modelo": "logistica", "C": 1.0, "class_weight": "balanced"},
        {"modelo": "hist_gradient_boosting", "learning_rate": 0.05, "max_iter": 400,
         "max_leaf_nodes": 63, "etapas": 5},
    ],
    "regresion_tabular": [
        {"modelo": "hist_gradient_boosting", "learning_rate": 0.1, "max_iter": 200,
         "max_leaf_nodes": 31, "etapas": 5},
        {"modelo": "random_forest", "n_estimators": 400, "max_depth": None,
         "min_samples_leaf": 2, "etapas": 5},
        {"modelo": "ridge", "alpha": 1.0},
        {"modelo": "hist_gradient_boosting", "learning_rate": 0.05, "max_iter": 400,
         "max_leaf_nodes": 63, "etapas": 5},
    ],
    "clasificacion_texto": [
        {"modelo": "tfidf_svm", "C": 1.0, "max_features": 30000, "ngram_max": 2},
        {"modelo": "tfidf_logistica", "C": 4.0, "max_features": 50000, "ngram_max": 2,
         "class_weight": "balanced"},
        {"modelo": "tfidf_nb", "alpha": 0.5, "max_features": 30000, "ngram_max": 1},
    ],
}

METRICAS_OBJETIVO = {
    "clasificacion_tabular": ["f1_macro", "accuracy", "f1_ponderado", "recall_macro",
                              "precision_macro"],
    "clasificacion_texto": ["f1_macro", "accuracy", "f1_ponderado", "recall_macro",
                            "precision_macro"],
    "regresion_tabular": ["r2"],
}


def es_clasificacion(tipo_tarea: str) -> bool:
    return tipo_tarea.startswith("clasificacion")


def _clave(hp: dict) -> tuple:
    ignorar = {"batch_size"}
    return tuple(sorted((k, repr(v)) for k, v in hp.items() if k not in ignorar))


def siguiente_de_rejilla(tipo_tarea: str, probados: list[dict]) -> dict | None:
    """Primera combinación de la rejilla que aún no se ha probado."""
    vistos = {_clave(h) for h in probados}
    for combinacion in REJILLAS.get(tipo_tarea, []):
        if _clave(combinacion) not in vistos:
            return dict(combinacion)
    return None
