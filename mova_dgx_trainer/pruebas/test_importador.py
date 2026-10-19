import pandas as pd
import pytest

from nucleo import importador
from nucleo.contexto import Contexto
from nucleo.importador import OpcionesImportacion


def test_csv_detecta_delimitador_y_codificacion(recursos):
    r = importador.importar_fichero(recursos["csv"])
    assert r.estado in ("importado", "avisos"), r.error
    assert r.delimitador == ";"
    assert r.codificacion == "utf-8"
    assert r.df.shape == (60, 5)
    assert list(r.df.columns) == ["edad", "ingresos", "zona", "antiguedad", "compra"]
    assert r.hash and len(r.hash) == 64


def test_csv_latin1(recursos):
    r = importador.importar_fichero(recursos["csv_latin1"])
    assert r.codificacion == "latin-1"
    assert r.df["nombre"].tolist() == ["Peña", "Ibáñez", "Muñoz"]


def test_xlsx_primera_hoja_y_hojas_elegidas(recursos):
    r = importador.importar_fichero(recursos["xlsx"])
    assert r.df.shape == (60, 5)
    assert r.hojas_disponibles == ["Datos", "Resumen"]
    assert r.estado == "avisos"  # avisa de que hay más hojas
    r2 = importador.importar_fichero(recursos["xlsx"], OpcionesImportacion(hojas=["*"]))
    assert len(r2.df) == 65 and "hoja" in r2.df.columns
    r3 = importador.importar_fichero(recursos["xlsx"], OpcionesImportacion(hojas=["Resumen"]))
    assert len(r3.df) == 5


def test_txt_delimitado(recursos):
    r = importador.importar_fichero(recursos["txt_delimitado"])
    assert r.delimitador == "\t"
    assert r.df.shape == (60, 5)


def test_txt_libre(recursos):
    r = importador.importar_fichero(recursos["txt_libre"])
    assert r.delimitador is None
    assert list(r.df.columns) == ["texto", "origen"]
    assert len(r.df) == 4  # la línea vacía se descarta
    assert (r.df["origen"] == "notas.txt").all()


def test_json_lista(recursos):
    r = importador.importar_fichero(recursos["json_lista"])
    assert r.df.shape == (20, 5)


def test_jsonl(recursos):
    r = importador.importar_fichero(recursos["jsonl"])
    assert r.formato == "jsonl"
    assert r.df.shape == (20, 5)


def test_json_anidado_se_normaliza(recursos):
    r = importador.importar_fichero(recursos["json_anidado"])
    assert "cliente.nombre" in r.df.columns
    assert any("$.datos" in a for a in r.avisos)


def test_json_con_campos_lista_se_importa(tmp_path):
    """Regresión: una lista en una celda descartaba el fichero (unhashable type: 'list')."""
    import json
    ruta = tmp_path / "listas.json"
    ruta.write_text(json.dumps([{"id": i, "etiquetas": ["a", "b"], "meta": {"k": [i]}}
                                for i in range(10)]), encoding="utf-8")
    r = importador.importar_fichero(ruta)
    assert r.estado != "descartado", r.error
    assert r.df["etiquetas"].iloc[0] == '["a", "b"]'
    assert importador.hash_dataframe(r.df)
    assert importador.resumen_columnas(r.df)


def test_json_no_tabulable_indica_nodo_y_admite_texto(recursos):
    r = importador.importar_fichero(recursos["json_no_tabulable"])
    assert r.estado == "descartado"
    assert r.nodo_no_tabulable == "$.registros[2]"
    r2 = importador.importar_fichero(recursos["json_no_tabulable"],
                                     OpcionesImportacion(json_como_texto=True))
    assert r2.df is not None and "texto" in r2.df.columns


def test_lote_no_aborta_y_resume(recursos, tmp_path):
    malo = tmp_path / "roto.xlsx"
    malo.write_bytes(b"esto no es un excel")
    resumen = importador.importar_lote([recursos["csv"], malo, recursos["json_lista"]])
    assert resumen.descartados == 1
    assert len(resumen.validos) == 2
    assert "descartados: 1" in resumen.texto()


def test_carpeta_y_esquemas(recursos, tmp_path):
    for nombre in ("a.csv", "b.csv"):
        pd.DataFrame({"x": [1, 2], "y": [3, 4]}).to_csv(tmp_path / nombre, index=False)
    pd.DataFrame({"x": [5], "z": [6]}).to_csv(tmp_path / "c.csv", index=False)
    resumen = importador.importar_lote([tmp_path])
    assert len(resumen.resultados) == 3
    compatible, dif = importador.comparar_esquemas(resumen.resultados)
    assert not compatible
    assert dif["por_fichero"]["c.csv"]["faltan"] == ["y"]
    with pytest.raises(importador.ErrorImportacion):
        importador.combinar(resumen.resultados, "compatible")
    assert list(importador.combinar(resumen.resultados, "interseccion").columns) == ["x"]
    assert importador.combinar(resumen.resultados, "union").shape == (5, 3)


def test_carpeta_sin_ficheros_admitidos_lo_explica(tmp_path):
    """Regresión: una carpeta de PDF y Word terminaba en «Importados: 0» sin explicación."""
    (tmp_path / "memoria.pdf").write_bytes(b"%PDF")
    (tmp_path / "anexo.docx").write_bytes(b"PK")
    (tmp_path / "otro.pdf").write_bytes(b"%PDF")
    mensajes = []
    resumen = importador.importar_lote([tmp_path], ctx=Contexto(al_log=mensajes.append))
    assert resumen.resultados == []
    assert "se omiten 3 de otros tipos (2 .pdf, 1 .docx)" in resumen.avisos[0]
    assert "No hay ningún fichero que importar" in resumen.avisos[-1]
    assert any("se omiten 3" in m for m in mensajes)


def test_validacion_marca_problemas():
    df = pd.DataFrame({"a": [1, 1, 1, 1], "b": [None, None, None, 2], "c": [1, 2, 3, 3]})
    v = importador.validar(pd.concat([df, df.head(1)]))
    assert "a" in v.constantes
    assert v.duplicados == 1
    assert any("nulos" in t for _, t in v.problemas)
    assert not v.bloquea
    assert importador.validar(pd.DataFrame()).bloquea
