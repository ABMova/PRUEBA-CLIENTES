"""Preparador: limpieza, especificación de codificación/escalado y división.

La codificación y el escalado se AJUSTAN dentro del script de entrenamiento
(solo con train, sin fuga de información), siguiendo la especificación que
genera este módulo. Aquí se limpia, se tipan las columnas y se divide.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import pandas as pd
from sklearn.model_selection import train_test_split

from nucleo.rejillas import es_clasificacion


class ErrorPreparacion(Exception):
    pass


@dataclass
class ConfigPreparacion:
    objetivo: str = ""
    columna_texto: str = ""
    columnas_excluidas: list = field(default_factory=list)
    eliminar_duplicados: bool = True
    eliminar_constantes: bool = True
    imputacion_numerica: str = "mediana"     # mediana | media | cero
    imputacion_categorica: str = "moda"      # moda | constante
    escalado: str = "estandar"               # estandar | minmax | ninguno
    codificacion: str = "onehot"             # onehot | ordinal
    max_categorias: int = 50
    proporciones: tuple = (0.70, 0.15, 0.15)
    semilla: int = 42
    estratificar: bool = True

    def como_dict(self) -> dict:
        d = asdict(self)
        d["proporciones"] = list(self.proporciones)
        return d


@dataclass
class ResultadoPreparacion:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    especificacion: dict
    avisos: list
    division: dict


def validar_proporciones(proporciones) -> tuple[float, float, float]:
    tr, va, te = (float(x) for x in proporciones)
    if min(tr, va, te) <= 0 or abs(tr + va + te - 1.0) > 1e-6:
        raise ErrorPreparacion("Las proporciones deben ser positivas y sumar 100 %.")
    return tr, va, te


def _partir(df: pd.DataFrame, objetivo: str, fraccion_val: float, fraccion_test: float,
            semilla: int, estratificar: bool):
    resto, test = train_test_split(df, test_size=fraccion_test, random_state=semilla,
                                   stratify=df[objetivo] if estratificar else None)
    train, val = train_test_split(resto, test_size=fraccion_val, random_state=semilla,
                                  stratify=resto[objetivo] if estratificar else None)
    return train, val, test


def dividir(df: pd.DataFrame,objetivo: str, proporciones=(0.70, 0.15, 0.15),
            semilla: int = 42, estratificar: bool = True) -> tuple[pd.DataFrame, pd.DataFrame,
                                                                  pd.DataFrame, dict]:
    """División train/val/test reproducible; estratificada si se pide y es posible."""
    tr, va, te = validar_proporciones(proporciones)
    info = {"proporciones": [tr, va, te], "semilla": semilla, "estratificada": False}
    estratificada = False
    if estratificar:
        conteo = df[objetivo].value_counts()
        # cada clase necesita al menos un ejemplo por partición, y cada partición
        # tantas filas como clases (scikit-learn lo exige)
        n_test = math.ceil(te * len(df))
        n_val = math.ceil(va / (tr + va) * (len(df) - n_test))
        if len(conteo) < 2 or conteo.min() < 3:
            info["aviso"] = "No se puede estratificar: hay clases con menos de 3 ejemplos."
        elif min(n_test, n_val) < len(conteo):
            info["aviso"] = (f"No se puede estratificar: hay {len(conteo)} clases y validación "
                             f"o test solo tienen {min(n_test, n_val)} filas.")
        else:
            estratificada = True
    try:
        train, val, test = _partir(df, objetivo, va / (tr + va), te, semilla, estratificada)
    except ValueError as e:
        if not estratificada:
            raise ErrorPreparacion(f"No se puede dividir el dataset ({e}).") from e
        estratificada = False
        info["aviso"] = "No se puede estratificar con estas proporciones; se divide sin estratificar."
        train, val, test = _partir(df, objetivo, va / (tr + va), te, semilla, False)
    info["estratificada"] = estratificada
    info["filas"] = {"train": len(train), "val": len(val), "test": len(test)}
    return (train.reset_index(drop=True), val.reset_index(drop=True),
            test.reset_index(drop=True), info)


def preparar(df: pd.DataFrame, tipo_tarea: str, config: ConfigPreparacion) -> ResultadoPreparacion:
    avisos: list[str] = []
    if not config.objetivo or config.objetivo not in df.columns:
        raise ErrorPreparacion("Elija la columna objetivo antes de preparar el dataset.")
    clasif = es_clasificacion(tipo_tarea)
    datos = df.copy()

    excluidas = [c for c in config.columnas_excluidas if c in datos.columns and c != config.objetivo]
    if excluidas:
        datos = datos.drop(columns=excluidas)

    n = len(datos)
    datos = datos[datos[config.objetivo].notna()]
    if len(datos) < n:
        avisos.append(f"Se eliminan {n - len(datos)} filas sin valor en el objetivo.")

    if config.eliminar_duplicados:
        n = len(datos)
        datos = datos.drop_duplicates()
        if len(datos) < n:
            avisos.append(f"Se eliminan {n - len(datos)} filas duplicadas.")

    if not clasif:
        objetivo_num = pd.to_numeric(datos[config.objetivo], errors="coerce")
        if objetivo_num.isna().any():
            raise ErrorPreparacion(f"La columna objetivo «{config.objetivo}» tiene valores no "
                                   "numéricos y la tarea es de regresión.")
        datos[config.objetivo] = objetivo_num
    else:
        datos[config.objetivo] = datos[config.objetivo].astype(str)
        clases = datos[config.objetivo].nunique()
        if clases < 2:
            raise ErrorPreparacion("La columna objetivo tiene una sola clase: no hay nada que "
                                   "clasificar.")
        if clases > 100:
            avisos.append(f"El objetivo tiene {clases} clases: revise si es la columna correcta.")

    numericas, categoricas, descartadas = [], [], []
    texto = ""
    if tipo_tarea == "clasificacion_texto":
        texto = config.columna_texto or next(
            (c for c in datos.columns if c != config.objetivo and
             not pd.api.types.is_numeric_dtype(datos[c])), "")
        if not texto or texto not in datos.columns:
            raise ErrorPreparacion("Elija la columna de texto para la clasificación de texto.")
        datos[texto] = datos[texto].fillna("").astype(str)
        datos = datos[[texto, config.objetivo]]
    else:
        for c in datos.columns:
            if c == config.objetivo:
                continue
            serie = datos[c]
            if config.eliminar_constantes and serie.nunique(dropna=True) <= 1:
                descartadas.append(c)
                continue
            if pd.api.types.is_bool_dtype(serie):
                datos[c] = serie.astype(int)
                numericas.append(c)
            elif pd.api.types.is_numeric_dtype(serie):
                numericas.append(c)
            else:
                convertida = pd.to_numeric(serie, errors="coerce")
                if serie.notna().sum() and convertida.notna().sum() / serie.notna().sum() > 0.95:
                    datos[c] = convertida
                    numericas.append(c)
                    continue
                unicos = serie.nunique(dropna=True)
                if unicos > max(config.max_categorias, 0.5 * len(datos)):
                    descartadas.append(c)
                    avisos.append(f"Columna «{c}» descartada: {unicos} valores distintos "
                                  "(parece un identificador o texto libre).")
                    continue
                categoricas.append(c)
        if descartadas:
            datos = datos.drop(columns=descartadas)
        if not numericas and not categoricas:
            raise ErrorPreparacion("No queda ninguna columna útil para entrenar.")

    if len(datos) < 20:
        raise ErrorPreparacion(f"Solo quedan {len(datos)} filas: se necesitan al menos 20.")

    train, val, test, division = dividir(datos, config.objetivo, config.proporciones,
                                         config.semilla, config.estratificar and clasif)
    if division.get("aviso"):
        avisos.append(division["aviso"])

    especificacion = {
        "objetivo": config.objetivo, "numericas": numericas, "categoricas": categoricas,
        "texto": texto, "descartadas": descartadas + excluidas,
        "imputacion_numerica": config.imputacion_numerica,
        "imputacion_categorica": config.imputacion_categorica,
        "escalado": config.escalado, "codificacion": config.codificacion,
        "max_categorias": config.max_categorias,
    }
    return ResultadoPreparacion(train, val, test, especificacion, avisos, division)
