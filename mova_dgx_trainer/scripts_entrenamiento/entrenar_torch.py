"""Entrenamiento con PyTorch (MLP para datos tabulares). [PENDIENTE: no verificado]

Uso:  python entrenar_torch.py --config config.json --salida resultado.json

Mismo contrato que entrenar_sklearn.py. Solo tareas tabulares; la
clasificación de texto devuelve estado=error. Un error de memoria CUDA se
devuelve con el texto «CUDA out of memory» para que la app reduzca batch_size.
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
    for nombre in ("torch", "numpy", "pandas"):
        try:
            v[nombre] = __import__(nombre).__version__
        except Exception:  # noqa: BLE001
            v[nombre] = None
    try:
        import torch
        v["cuda"] = torch.version.cuda
        v["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:  # noqa: BLE001
        pass
    return v


def tabular(train, val, test, espec):
    """One-hot y estandarización con estadísticos de train (sin fuga)."""
    import numpy as np
    import pandas as pd

    num, cat = list(espec.get("numericas", [])), list(espec.get("categoricas", []))
    partes = []
    for d in (train, val, test):
        x = d[num + cat].copy()
        for c in cat:
            x[c] = x[c].astype(str)
        partes.append(x)
    medias = partes[0][num].astype(float).median() if num else None
    columnas_dummy = None
    salida = []
    for x in partes:
        if num:
            x[num] = x[num].astype(float).fillna(medias)
        x = pd.get_dummies(x, columns=cat, dtype=float)
        if columnas_dummy is None:
            columnas_dummy = list(x.columns)
        x = x.reindex(columns=columnas_dummy, fill_value=0.0)
        salida.append(x.to_numpy(dtype=np.float32))
    mu, sd = salida[0].mean(axis=0), salida[0].std(axis=0) + 1e-8
    return [(s - mu) / sd for s in salida]


def entrenar(config: dict, carpeta: Path) -> dict:
    import numpy as np
    import pandas as pd
    import torch
    from torch import nn

    tipo = config["tipo_tarea"]
    if tipo == "clasificacion_texto":
        raise ValueError("entrenar_torch.py no admite clasificación de texto.")
    espec, hp = config["especificacion"], dict(config.get("hiperparametros") or {})
    semilla = int(config.get("semilla", 42))
    torch.manual_seed(semilla)
    np.random.seed(semilla)
    objetivo = espec["objetivo"]
    leer = lambda n: pd.read_csv(carpeta / config["ficheros"][n], encoding="utf-8")  # noqa: E731
    train, val, test = leer("train"), leer("val"), leer("test")
    x_tr, x_va, x_te = tabular(train, val, test, espec)
    clasif = tipo.startswith("clasificacion")
    if clasif:
        clases = sorted(train[objetivo].astype(str).unique())
        indice = {c: i for i, c in enumerate(clases)}
        y = [d[objetivo].astype(str).map(indice).fillna(-1).astype(int).to_numpy()
             for d in (train, val, test)]
        salida_n, criterio = len(clases), nn.CrossEntropyLoss()
    else:
        y = [d[objetivo].astype(float).to_numpy(dtype=np.float32) for d in (train, val, test)]
        salida_n, criterio = 1, nn.MSELoss()

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"Dispositivo: {dispositivo}")
    capas, entrada = [], x_tr.shape[1]
    for n in hp.get("capas_ocultas", [128, 64]):
        capas += [nn.Linear(entrada, int(n)), nn.ReLU(), nn.Dropout(float(hp.get("dropout", 0.1)))]
        entrada = int(n)
    capas.append(nn.Linear(entrada, salida_n))
    modelo = nn.Sequential(*capas).to(dispositivo)
    opt = torch.optim.Adam(modelo.parameters(), lr=float(hp.get("tasa_aprendizaje", 1e-3)))
    epocas, lote = int(hp.get("epocas", 20)), int(hp.get("batch_size", 64))

    def tensor_y(v):
        return torch.tensor(v, dtype=torch.long if clasif else torch.float32)

    xt, yt = torch.tensor(x_tr), tensor_y(y[0])
    xv = torch.tensor(x_va).to(dispositivo)

    def predecir(x):
        modelo.eval()
        with torch.no_grad():
            s = modelo(x)
        modelo.train()
        return s

    for epoca in range(1, epocas + 1):
        orden = torch.randperm(len(xt))
        total = 0.0
        for i in range(0, len(xt), lote):
            idx = orden[i:i + lote]
            xb, yb = xt[idx].to(dispositivo), yt[idx].to(dispositivo)
            opt.zero_grad()
            s = modelo(xb)
            perdida = criterio(s, yb) if clasif else criterio(s.squeeze(1), yb)
            perdida.backward()
            opt.step()
            total += float(perdida) * len(idx)
        sv = predecir(xv).cpu()
        if clasif:
            metrica = float((sv.argmax(1).numpy() == y[1]).mean())
        else:
            p = sv.squeeze(1).numpy()
            metrica = float(1 - ((y[1] - p) ** 2).sum() / max(((y[1] - y[1].mean()) ** 2).sum(), 1e-12))
        emitir("progreso", epoca=epoca, total=epocas, perdida=total / len(xt), metrica=metrica)

    st = predecir(torch.tensor(x_te).to(dispositivo)).cpu()
    pred = pd.DataFrame({"y_real": test[objetivo]})
    if clasif:
        pred["y_pred"] = [clases[i] for i in st.argmax(1).numpy()]
        if salida_n == 2:
            pred["prob_positiva"] = torch.softmax(st, 1)[:, 1].numpy()
        metricas = {"accuracy": float((pred["y_pred"].astype(str) == pred["y_real"].astype(str)).mean())}
    else:
        pred["y_pred"] = st.squeeze(1).numpy()
        err = pred["y_real"].astype(float) - pred["y_pred"]
        metricas = {"mae": float(err.abs().mean()), "rmse": float(math.sqrt((err ** 2).mean()))}
    pred.to_csv(carpeta / "predicciones_test.csv", index=False, encoding="utf-8")
    torch.save(modelo.state_dict(), carpeta / "modelo.pt")
    return {"metricas": metricas, "ruta_modelo": "modelo.pt"}


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
            import torch  # noqa: F401
        except ImportError as e:
            raise RuntimeError("PyTorch no está instalado en el intérprete de ejecución.") from e
        resultado.update(entrenar(config, ruta_config.parent))
        resultado["estado"] = "ok"
    except Exception as e:  # noqa: BLE001
        texto = f"{type(e).__name__}: {e}"
        if "out of memory" in str(e).lower() and "cuda" in str(e).lower():
            texto = f"CUDA out of memory: {e}"
        resultado["error"] = texto
        log(traceback.format_exc())
    resultado["duracion_s"] = round(time.time() - inicio, 3)
    Path(args.salida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
                                 encoding="utf-8")
    return 0 if resultado["estado"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
