"""Genera los ficheros de prueba de pruebas/recursos/ (deterministas, semilla 42)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

CARPETA = Path(__file__).resolve().parent


def datos_clasificacion(n: int = 400, semilla: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    edad = rng.integers(18, 70, n)
    ingresos = rng.normal(30000, 8000, n).round(2)
    zona = rng.choice(["norte", "sur", "este", "oeste"], n)
    antiguedad = rng.integers(0, 20, n)
    puntuacion = 0.04 * (edad - 40) + (ingresos - 30000) / 6000 + (zona == "norte") * 1.2 \
        + rng.normal(0, 0.6, n)
    clase = np.where(puntuacion > 0.3, "si", "no")
    return pd.DataFrame({"edad": edad, "ingresos": ingresos, "zona": zona,
                         "antiguedad": antiguedad, "compra": clase})


def generar(carpeta: Path = CARPETA, forzar: bool = False) -> dict[str, Path]:
    """Escribe los ficheros que falten (o todos con forzar=True).

    No se reescriben en cada ejecución: el .xlsx guarda la fecha de creación y
    cambiaría en el repositorio sin motivo.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    df = datos_clasificacion(60)
    rutas = {
        "csv": carpeta / "clientes.csv",
        "xlsx": carpeta / "clientes.xlsx",
        "txt_delimitado": carpeta / "clientes_tab.txt",
        "txt_libre": carpeta / "notas.txt",
        "json_lista": carpeta / "clientes.json",
        "jsonl": carpeta / "clientes.jsonl",
        "json_anidado": carpeta / "anidado.json",
        "json_no_tabulable": carpeta / "no_tabulable.json",
        "csv_latin1": carpeta / "latin1.csv",
    }
    if not forzar and all(r.exists() for r in rutas.values()):
        return rutas
    df.to_csv(rutas["csv"], index=False, sep=";", encoding="utf-8")
    with pd.ExcelWriter(rutas["xlsx"]) as w:
        df.to_excel(w, sheet_name="Datos", index=False)
        df.head(5).to_excel(w, sheet_name="Resumen", index=False)
    df.to_csv(rutas["txt_delimitado"], index=False, sep="\t", encoding="utf-8")
    rutas["txt_libre"].write_text(
        "Primera nota sobre el cliente, con comas, y puntos.\n"
        "Segunda nota: sin estructura fija\n\n"
        "Tercera; con un punto y coma suelto\n"
        "Cuarta nota más larga que las demás para romper cualquier patrón\n",
        encoding="utf-8")
    registros = df.head(20).to_dict(orient="records")
    rutas["json_lista"].write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    rutas["jsonl"].write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in registros),
                              encoding="utf-8")
    rutas["json_anidado"].write_text(json.dumps(
        {"meta": {"version": 1}, "datos": [{"id": i, "cliente": {"nombre": f"c{i}", "pais": "ES"}}
                                           for i in range(5)]}), encoding="utf-8")
    rutas["json_no_tabulable"].write_text(json.dumps(
        {"registros": [{"a": 1}, {"a": 2}, "texto suelto"]}), encoding="utf-8")
    pd.DataFrame({"nombre": ["Peña", "Ibáñez", "Muñoz"], "valor": [1, 2, 3]}).to_csv(
        rutas["csv_latin1"], index=False, encoding="latin-1")
    return rutas


if __name__ == "__main__":
    for k, v in generar(forzar=True).items():
        print(f"{k}: {v}")
