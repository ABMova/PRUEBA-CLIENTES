import pandas as pd
import pytest

from nucleo import evaluador, preparador
from nucleo.preparador import ConfigPreparacion
from pruebas.recursos.generar import datos_clasificacion


def test_division_reproducible_con_semilla():
    df = datos_clasificacion(300)
    a = preparador.dividir(df, "compra", (0.7, 0.15, 0.15), 42, True)
    b = preparador.dividir(df, "compra", (0.7, 0.15, 0.15), 42, True)
    c = preparador.dividir(df, "compra", (0.7, 0.15, 0.15), 7, True)
    for x, y in zip(a[:3], b[:3]):
        pd.testing.assert_frame_equal(x, y)
    assert not a[0].equals(c[0])
    assert a[3]["filas"] == {"train": 210, "val": 45, "test": 45}
    assert a[3]["estratificada"] is True
    # la proporción de clases se conserva en cada partición
    total = df["compra"].value_counts(normalize=True)
    for parte in a[:3]:
        prop = parte["compra"].value_counts(normalize=True)
        assert abs(prop["si"] - total["si"]) < 0.05


def test_proporciones_invalidas():
    with pytest.raises(preparador.ErrorPreparacion):
        preparador.validar_proporciones((0.8, 0.15, 0.15))


def test_preparar_tipa_columnas():
    df = datos_clasificacion(200)
    df["id_cliente"] = [f"C{i}" for i in range(len(df))]
    df["constante"] = 1
    r = preparador.preparar(df, "clasificacion_tabular", ConfigPreparacion(objetivo="compra"))
    e = r.especificacion
    assert set(e["numericas"]) == {"edad", "ingresos", "antiguedad"}
    assert e["categoricas"] == ["zona"]
    assert "id_cliente" in e["descartadas"] and "constante" in e["descartadas"]


def test_linea_base_clasificacion():
    train = pd.DataFrame({"y": ["a"] * 7 + ["b"] * 3, "x": range(10)})
    test = pd.DataFrame({"y": ["a", "a", "b", "b"], "x": range(4)})
    base = evaluador.calcular_linea_base(train, test, "y", "clasificacion_tabular")
    assert base["estrategia"] == "most_frequent"
    assert base["accuracy"] == 0.5
    assert base["f1_macro"] == pytest.approx(1 / 3, abs=1e-6)
    assert base["roc_auc"] == 0.5


def test_linea_base_regresion():
    train = pd.DataFrame({"y": [1.0, 2.0, 3.0]})
    test = pd.DataFrame({"y": [2.0, 4.0]})
    base = evaluador.calcular_linea_base(train, test, "y", "regresion_tabular")
    assert base["mae"] == pytest.approx(1.0)
    assert base["estrategia"] == "mean"


def test_veredictos_por_defecto():
    base = {"f1_macro": 0.40}
    assert evaluador.veredicto("clasificacion_tabular", {"f1_macro": 0.80}, base)["veredicto"] == "aprobado"
    v = evaluador.veredicto("clasificacion_tabular", {"f1_macro": 0.72}, {"f1_macro": 0.65})
    assert v["veredicto"] == "insuficiente"  # no supera baseline + 0.10
    base_r = {"mae": 10.0, "r2": 0.0}
    assert evaluador.veredicto("regresion_tabular", {"r2": 0.6, "mae": 8.9}, base_r)["veredicto"] == "aprobado"
    assert evaluador.veredicto("regresion_tabular", {"r2": 0.6, "mae": 9.5}, base_r)["veredicto"] == "insuficiente"
