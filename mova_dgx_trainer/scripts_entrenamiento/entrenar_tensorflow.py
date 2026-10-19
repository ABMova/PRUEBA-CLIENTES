"""Entrenamiento con TensorFlow/Keras (MLP para datos tabulares). [PENDIENTE: no verificado]

Uso:  python entrenar_tensorflow.py --config config.json --salida resultado.json

Mismo contrato que entrenar_sklearn.py. Solo tareas tabulares.
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
    for nombre in ("tensorflow", "numpy", "pandas"):
        try:
            v[nombre] = __import__(nombre).__version__
        except Exception:  # noqa: BLE001
            v[nombre] = None
    return v


def tabular(train, val, test, espec):
    import numpy as np
    import pandas as pd

    num, cat = list(espec.get("numericas", [])), list(espec.get("categoricas", []))
    medias = train[num].astype(float).median() if num else None
    columnas, salida = None, []
    for d in (train, val, test):
        x = d[num + cat].copy()
        for c in cat:
            x[c] = x[c].astype(str)
        if num:
            x[num] = x[num].astype(float).fillna(medias)
        x = pd.get_dummies(x, columns=cat, dtype=float)
        columnas = columnas or list(x.columns)
        salida.append(x.reindex(columns=columnas, fill_value=0.0).to_numpy(dtype=np.float32))
    mu, sd = salida[0].mean(axis=0), salida[0].std(axis=0) + 1e-8
    return [(s - mu) / sd for s in salida]


def entrenar(config: dict, carpeta: Path) -> dict:
    import pandas as pd
    import tensorflow as tf

    tipo = config["tipo_tarea"]
    if tipo == "clasificacion_texto":
        raise ValueError("entrenar_tensorflow.py no admite clasificación de texto.")
    espec, hp = config["especificacion"], dict(config.get("hiperparametros") or {})
    tf.keras.utils.set_random_seed(int(config.get("semilla", 42)))
    objetivo = espec["objetivo"]
    leer = lambda n: pd.read_csv(carpeta / config["ficheros"][n], encoding="utf-8")  # noqa: E731
    train, val, test = leer("train"), leer("val"), leer("test")
    x_tr, x_va, x_te = tabular(train, val, test, espec)
    clasif = tipo.startswith("clasificacion")
    if clasif:
        clases = sorted(train[objetivo].astype(str).unique())
        indice = {c: i for i, c in enumerate(clases)}
        y_tr, y_va = (d[objetivo].astype(str).map(indice).fillna(0).astype(int).to_numpy()
                      for d in (train, val))
    else:
        y_tr, y_va = (d[objetivo].astype(float).to_numpy() for d in (train, val))

    capas = [tf.keras.Input(shape=(x_tr.shape[1],))]
    for n in hp.get("capas_ocultas", [128, 64]):
        capas += [tf.keras.layers.Dense(int(n), activation="relu"),
                  tf.keras.layers.Dropout(float(hp.get("dropout", 0.1)))]
    capas.append(tf.keras.layers.Dense(len(clases) if clasif else 1))
    modelo = tf.keras.Sequential(capas)
    modelo.compile(optimizer=tf.keras.optimizers.Adam(float(hp.get("tasa_aprendizaje", 1e-3))),
                   loss=(tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
                         if clasif else "mse"),
                   metrics=["accuracy"] if clasif else ["mae"])
    epocas = int(hp.get("epocas", 20))

    class Progreso(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            logs = logs or {}
            emitir("progreso", epoca=epoch + 1, total=epocas, perdida=logs.get("loss"),
                   metrica=logs.get("val_accuracy", logs.get("val_mae")))

    modelo.fit(x_tr, y_tr, validation_data=(x_va, y_va), epochs=epocas,
               batch_size=int(hp.get("batch_size", 64)), verbose=0, callbacks=[Progreso()])
    salida = modelo.predict(x_te, verbose=0)
    pred = pd.DataFrame({"y_real": test[objetivo]})
    if clasif:
        pred["y_pred"] = [clases[i] for i in salida.argmax(1)]
        if len(clases) == 2:
            pred["prob_positiva"] = tf.nn.softmax(salida, axis=1).numpy()[:, 1]
        metricas = {"accuracy": float((pred["y_pred"] == pred["y_real"].astype(str)).mean())}
    else:
        pred["y_pred"] = salida[:, 0]
        err = pred["y_real"].astype(float) - pred["y_pred"]
        metricas = {"mae": float(err.abs().mean()), "rmse": float(math.sqrt((err ** 2).mean()))}
    pred.to_csv(carpeta / "predicciones_test.csv", index=False, encoding="utf-8")
    modelo.save(carpeta / "modelo.keras")
    return {"metricas": metricas, "ruta_modelo": "modelo.keras"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--salida", required=True)
    args = parser.parse_args(argv)
    inicio = time.time()
    ruta_config = Path(args.config).resolve()
    resultado = {"estado": "error", "metricas": {}, "ruta_modelo": None, "duracion_s": 0.0,
                 "hiperparametros": {}, "versiones": versiones(), "error": None}
    try:
        config = json.loads(ruta_config.read_text(encoding="utf-8"))
        resultado["hiperparametros"] = config.get("hiperparametros") or {}
        try:
            import tensorflow  # noqa: F401
        except ImportError as e:
            raise RuntimeError("TensorFlow no está instalado en el intérprete de ejecución.") from e
        resultado.update(entrenar(config, ruta_config.parent))
        resultado["estado"] = "ok"
    except Exception as e:  # noqa: BLE001
        texto = f"{type(e).__name__}: {e}"
        if "RESOURCE_EXHAUSTED" in str(e) or "OOM" in str(e):
            texto = f"RESOURCE_EXHAUSTED OOM (CUDA out of memory): {e}"
        resultado["error"] = texto
        log(traceback.format_exc())
    resultado["duracion_s"] = round(time.time() - inicio, 3)
    Path(args.salida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
                                 encoding="utf-8")
    return 0 if resultado["estado"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
