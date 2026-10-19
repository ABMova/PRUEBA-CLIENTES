"""Entrenamiento con scikit-learn. Autocontenido: se copia tal cual a la DGX Spark.

Uso:  python entrenar_sklearn.py --config config.json --salida resultado.json

Por stdout emite una línea JSON por evento:
  {"evento":"progreso","epoca":3,"total":5,"perdida":0.41,"metrica":0.78}
  {"evento":"log","texto":"..."}
Escribe en la carpeta de la configuración `modelo.joblib` y
`predicciones_test.csv`, y en --salida el resultado con las claves estado,
metricas, ruta_modelo, duracion_s, hiperparametros, versiones y error.
Código de salida 0 solo si estado == ok.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
import traceback
from pathlib import Path


def emitir(evento: str, **datos) -> None:
    print(json.dumps({"evento": evento, **datos}, ensure_ascii=False, default=str), flush=True)


def log(texto: str) -> None:
    emitir("log", texto=texto)


def versiones() -> dict:
    v = {"python": platform.python_version(), "plataforma": platform.platform()}
    for nombre in ("sklearn", "numpy", "pandas", "joblib", "scipy"):
        try:
            v[nombre] = __import__(nombre).__version__
        except Exception:  # noqa: BLE001
            v[nombre] = None
    return v


def es_clasificacion(tipo: str) -> bool:
    return tipo.startswith("clasificacion")


def construir_preprocesador(espec: dict, tipo: str):
    from sklearn.compose import ColumnTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, OrdinalEncoder, StandardScaler

    hp = espec.get("_hp", {})
    if tipo == "clasificacion_texto":
        vectorizador = TfidfVectorizer(max_features=int(hp.get("max_features", 20000)),
                                       ngram_range=(1, int(hp.get("ngram_max", 2))),
                                       sublinear_tf=True)
        return ColumnTransformer([("texto", vectorizador, espec["texto"])])

    transformadores = []
    if espec.get("numericas"):
        estrategia = {"mediana": "median", "media": "mean", "cero": "constant"}[
            espec.get("imputacion_numerica", "mediana")]
        pasos = [("imputar", SimpleImputer(strategy=estrategia, fill_value=0))]
        if espec.get("escalado") == "estandar":
            pasos.append(("escalar", StandardScaler()))
        elif espec.get("escalado") == "minmax":
            pasos.append(("escalar", MinMaxScaler()))
        transformadores.append(("num", Pipeline(pasos), espec["numericas"]))
    if espec.get("categoricas"):
        estrategia = ("most_frequent" if espec.get("imputacion_categorica", "moda") == "moda"
                      else "constant")
        if espec.get("codificacion") == "ordinal":
            codificador = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        else:
            codificador = OneHotEncoder(handle_unknown="infrequent_if_exist", sparse_output=False,
                                        max_categories=int(espec.get("max_categorias", 50)))
        transformadores.append(("cat", Pipeline([
            ("imputar", SimpleImputer(strategy=estrategia, fill_value="desconocido")),
            ("codificar", codificador)]), espec["categoricas"]))
    return ColumnTransformer(transformadores, sparse_threshold=0.0)


def construir_modelo(tipo: str, hp: dict, semilla: int):
    from sklearn import ensemble, linear_model, naive_bayes, svm

    nombre = hp.get("modelo", "random_forest")
    clasif = es_clasificacion(tipo)
    cw = hp.get("class_weight")
    if tipo == "clasificacion_texto":
        if nombre == "tfidf_logistica":
            return linear_model.LogisticRegression(C=float(hp.get("C", 1.0)), max_iter=3000,
                                                   class_weight=cw, random_state=semilla)
        if nombre == "tfidf_svm":
            return svm.LinearSVC(C=float(hp.get("C", 1.0)), class_weight=cw, random_state=semilla)
        if nombre == "tfidf_nb":
            return naive_bayes.MultinomialNB(alpha=float(hp.get("alpha", 1.0)))
    elif nombre == "random_forest":
        clase = ensemble.RandomForestClassifier if clasif else ensemble.RandomForestRegressor
        args = dict(n_estimators=1, max_depth=hp.get("max_depth"),
                    min_samples_leaf=int(hp.get("min_samples_leaf", 1)),
                    random_state=semilla, n_jobs=-1, warm_start=True)
        if clasif:
            args["class_weight"] = cw
        return clase(**args)
    elif nombre == "hist_gradient_boosting":
        clase = (ensemble.HistGradientBoostingClassifier if clasif
                 else ensemble.HistGradientBoostingRegressor)
        return clase(learning_rate=float(hp.get("learning_rate", 0.1)), max_iter=1,
                     max_leaf_nodes=int(hp.get("max_leaf_nodes", 31)), early_stopping=False,
                     random_state=semilla, warm_start=True)
    elif nombre == "logistica" and clasif:
        return linear_model.LogisticRegression(C=float(hp.get("C", 1.0)), max_iter=3000,
                                               class_weight=cw, random_state=semilla)
    elif nombre == "ridge" and not clasif:
        return linear_model.Ridge(alpha=float(hp.get("alpha", 1.0)))
    raise ValueError(f"Modelo «{nombre}» no admitido para la tarea {tipo}.")


def plan_etapas(modelo, hp: dict) -> tuple[str | None, list[int]]:
    """Para modelos incrementales: parámetro a aumentar y valores por etapa."""
    nombre = hp.get("modelo")
    etapas = max(1, int(hp.get("etapas", 5)))
    if nombre == "random_forest":
        total, param = int(hp.get("n_estimators", 200)), "n_estimators"
    elif nombre == "hist_gradient_boosting":
        total, param = int(hp.get("max_iter", 200)), "max_iter"
    else:
        return None, [1]
    etapas = min(etapas, total)
    return param, [max(1, round(total * (i + 1) / etapas)) for i in range(etapas)]


def preparar_x(df, espec: dict, tipo: str):
    import numpy as np

    if tipo == "clasificacion_texto":
        return df[[espec["texto"]]].fillna("").astype(str)
    columnas = list(espec.get("numericas", [])) + list(espec.get("categoricas", []))
    x = df[columnas].copy()
    for c in espec.get("numericas", []):
        x[c] = x[c].astype(float)
    for c in espec.get("categoricas", []):
        serie = x[c]
        x[c] = serie.astype(str).astype(object).where(serie.notna(), np.nan)
    return x


def evaluar(tipo: str, y_real, y_pred, prob=None) -> dict:
    import numpy as np
    from sklearn import metrics as m

    if es_clasificacion(tipo):
        r = {"accuracy": m.accuracy_score(y_real, y_pred),
             "f1_macro": m.f1_score(y_real, y_pred, average="macro", zero_division=0),
             "f1_ponderado": m.f1_score(y_real, y_pred, average="weighted", zero_division=0)}
        if prob is not None and len(set(y_real)) == 2:
            try:
                positiva = sorted(set(y_real))[1]
                r["roc_auc"] = m.roc_auc_score((np.asarray(y_real) == positiva).astype(int), prob)
            except ValueError:
                pass
        return {k: float(v) for k, v in r.items()}
    return {"mae": float(m.mean_absolute_error(y_real, y_pred)),
            "rmse": float(math.sqrt(m.mean_squared_error(y_real, y_pred))),
            "r2": float(m.r2_score(y_real, y_pred))}


def perdida_val(tipo: str, modelo, x_val, y_val) -> float | None:
    from sklearn import metrics as m

    try:
        if es_clasificacion(tipo):
            if not hasattr(modelo, "predict_proba"):
                return None
            return float(m.log_loss(y_val, modelo.predict_proba(x_val), labels=modelo.classes_))
        return float(m.mean_squared_error(y_val, modelo.predict(x_val)))
    except ValueError:
        return None


def entrenar(config: dict, carpeta: Path) -> dict:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.pipeline import Pipeline

    tipo = config["tipo_tarea"]
    espec = dict(config["especificacion"])
    hp = dict(config.get("hiperparametros") or {})
    semilla = int(config.get("semilla", 42))
    espec["_hp"] = hp
    objetivo = espec["objetivo"]
    np.random.seed(semilla)

    def leer(nombre):
        return pd.read_csv(carpeta / config["ficheros"][nombre], encoding="utf-8", low_memory=False)

    train, val, test = leer("train"), leer("val"), leer("test")
    log(f"Datos: train={len(train)} val={len(val)} test={len(test)}")
    if es_clasificacion(tipo):
        y_tr, y_va, y_te = (d[objetivo].astype(str).to_numpy() for d in (train, val, test))
    else:
        y_tr, y_va, y_te = (d[objetivo].astype(float).to_numpy() for d in (train, val, test))
    x_tr, x_va, x_te = (preparar_x(d, espec, tipo) for d in (train, val, test))

    pre = construir_preprocesador(espec, tipo)
    t_tr = pre.fit_transform(x_tr)
    t_va = pre.transform(x_va)
    modelo = construir_modelo(tipo, hp, semilla)
    log(f"Modelo: {type(modelo).__name__} · rasgos tras preprocesado: {t_tr.shape[1]}")

    param, valores = plan_etapas(modelo, hp)
    nombre_metrica = config.get("metrica_objetivo") or ("f1_macro" if es_clasificacion(tipo) else "r2")
    for i, valor in enumerate(valores, 1):
        if param:
            modelo.set_params(**{param: valor})
        modelo.fit(t_tr, y_tr)
        pred_va = modelo.predict(t_va)
        met = evaluar(tipo, y_va, pred_va).get(nombre_metrica)
        if met is None and es_clasificacion(tipo):
            met = evaluar(tipo, y_va, pred_va)["f1_macro"]
        emitir("progreso", epoca=i, total=len(valores), perdida=perdida_val(tipo, modelo, t_va, y_va),
               metrica=met)

    tuberia = Pipeline([("preprocesado", pre), ("modelo", modelo)])
    pred_te = tuberia.predict(x_te)
    prob = None
    if es_clasificacion(tipo) and hasattr(modelo, "predict_proba") and len(modelo.classes_) == 2:
        prob = tuberia.predict_proba(x_te)[:, 1]
    predicciones = pd.DataFrame({"y_real": y_te, "y_pred": pred_te})
    if prob is not None:
        predicciones["prob_positiva"] = prob
    predicciones.to_csv(carpeta / "predicciones_test.csv", index=False, encoding="utf-8")
    joblib.dump(tuberia, carpeta / "modelo.joblib")
    return {"metricas": evaluar(tipo, y_te, pred_te, prob), "ruta_modelo": "modelo.joblib"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--salida", required=True)
    args = parser.parse_args(argv)
    inicio = time.time()
    ruta_config = Path(args.config).resolve()
    salida = Path(args.salida)
    if not salida.is_absolute():
        salida = Path.cwd() / salida
    resultado = {"estado": "error", "metricas": {}, "ruta_modelo": None, "duracion_s": 0.0,
                 "hiperparametros": {}, "versiones": versiones(), "error": None}
    try:
        config = json.loads(ruta_config.read_text(encoding="utf-8"))
        resultado["hiperparametros"] = config.get("hiperparametros") or {}
        log(f"Inicio · tarea {config.get('tipo_tarea')} · semilla {config.get('semilla')}")
        resultado.update(entrenar(config, ruta_config.parent))
        resultado["estado"] = "ok"
        log("Entrenamiento terminado.")
    except MemoryError:
        resultado["error"] = "Memoria insuficiente (MemoryError)."
        log(traceback.format_exc())
    except Exception as e:  # noqa: BLE001
        resultado["error"] = f"{type(e).__name__}: {e}"
        log(traceback.format_exc())
    resultado["duracion_s"] = round(time.time() - inicio, 3)
    salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
                      encoding="utf-8")
    return 0 if resultado["estado"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
