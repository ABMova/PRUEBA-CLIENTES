"""Importador: lectura, validación y normalización a un DataFrame canónico.

Formatos: CSV, Excel (xlsx/xlsm/xls), TXT (delimitado o libre) y JSON (lista de
objetos, objeto con una lista dentro, o JSON Lines). Un fichero que falla no
aborta el lote: queda como «descartado» con el motivo.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from nucleo.contexto import Cancelado, Contexto

EXTENSIONES = {".csv": "csv", ".tsv": "csv", ".xlsx": "excel", ".xlsm": "excel",
               ".xls": "excel", ".txt": "txt", ".json": "json", ".jsonl": "json",
               ".ndjson": "json"}
CODIFICACIONES = ("utf-8", "utf-8-sig", "latin-1")
DELIMITADORES = ",;\t|"
UMBRAL_TROZOS_BYTES = 200 * 1024 * 1024
UMBRAL_TROZOS_FILAS = 1_000_000
UMBRAL_MUESTREO_BYTES = 1024 * 1024 * 1024
TAMANO_TROZO = 50_000
UMBRAL_NULOS_AVISO = 0.30


class ErrorImportacion(Exception):
    pass


class ErrorNoTabulable(ErrorImportacion):
    def __init__(self, ruta_nodo: str, motivo: str):
        self.ruta_nodo = ruta_nodo
        super().__init__(f"JSON no tabulable en el nodo {ruta_nodo}: {motivo}. "
                         "Se puede importar como texto.")


@dataclass
class OpcionesImportacion:
    codificacion: str | None = None      # None = detectar
    delimitador: str | None = None       # None = detectar
    hojas: list[str] | None = None       # None = primera hoja; ["*"] = todas
    fila_cabecera: int = 0
    muestreo: str = "primeras"           # primeras | aleatoria (solo > 1 GB)
    n_muestreo: int = 200_000
    semilla: int = 42
    json_como_texto: bool = False


@dataclass
class Validacion:
    filas: int = 0
    columnas: int = 0
    tipos: dict = field(default_factory=dict)
    nulos_pct: dict = field(default_factory=dict)
    duplicados: int = 0
    constantes: list = field(default_factory=list)
    problemas: list = field(default_factory=list)   # [(nivel 'warn'|'err', texto)]

    @property
    def bloquea(self) -> bool:
        return any(n == "err" for n, _ in self.problemas)

    @property
    def tiene_avisos(self) -> bool:
        return any(n == "warn" for n, _ in self.problemas)

    def como_dict(self) -> dict:
        return {"filas": self.filas, "columnas": self.columnas, "tipos": self.tipos,
                "nulos_pct": self.nulos_pct, "duplicados": self.duplicados,
                "constantes": self.constantes, "problemas": self.problemas}


@dataclass
class ResultadoFichero:
    ruta: str
    formato: str = ""
    estado: str = "descartado"           # importado | avisos | descartado
    df: pd.DataFrame | None = None
    avisos: list = field(default_factory=list)
    error: str = ""
    codificacion: str | None = None
    delimitador: str | None = None
    hojas_disponibles: list = field(default_factory=list)
    hoja: str | None = None
    tamano: int = 0
    hash: str | None = None
    muestreado: bool = False
    nodo_no_tabulable: str | None = None
    validacion: Validacion | None = None

    @property
    def nombre(self) -> str:
        return Path(self.ruta).name

    @property
    def filas(self) -> int | None:
        return None if self.df is None else len(self.df)

    @property
    def columnas(self) -> int | None:
        return None if self.df is None else self.df.shape[1]


@dataclass
class ResumenLote:
    resultados: list[ResultadoFichero] = field(default_factory=list)

    def _contar(self, estado: str) -> int:
        return sum(1 for r in self.resultados if r.estado == estado)

    @property
    def importados(self) -> int:
        return self._contar("importado")

    @property
    def con_avisos(self) -> int:
        return self._contar("avisos")

    @property
    def descartados(self) -> int:
        return self._contar("descartado")

    @property
    def validos(self) -> list[ResultadoFichero]:
        return [r for r in self.resultados if r.df is not None]

    def texto(self) -> str:
        return (f"Importados: {self.importados} · con avisos: {self.con_avisos} · "
                f"descartados: {self.descartados}")


# --- utilidades ------------------------------------------------------------------

def hash_fichero(ruta: str | Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def hash_dataframe(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update("|".join(map(str, df.columns)).encode("utf-8"))
    h.update(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    return h.hexdigest()


def expandir_rutas(rutas: list[str | Path]) -> list[Path]:
    """Ficheros sueltos y carpetas (recorridas) con extensión admitida."""
    salida: list[Path] = []
    for r in rutas:
        p = Path(r)
        if p.is_dir():
            for raiz, _, ficheros in os.walk(p):
                for f in sorted(ficheros):
                    if Path(f).suffix.lower() in EXTENSIONES:
                        salida.append(Path(raiz) / f)
        elif p.suffix.lower() in EXTENSIONES:
            salida.append(p)
        else:
            salida.append(p)  # se descartará con su motivo
    vistos, unicas = set(), []
    for p in salida:
        clave = str(p.resolve()).lower()
        if clave not in vistos:
            vistos.add(clave)
            unicas.append(p)
    return unicas


def detectar_codificacion(ruta: str | Path, muestra: int = 1024 * 1024) -> str:
    """utf-8 → utf-8-sig → latin-1 (latin-1 nunca falla)."""
    with open(ruta, "rb") as f:
        datos = f.read(muestra)
    if datos.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    # el corte de la muestra puede partir un carácter multibyte: se toleran 3 bytes finales
    for recorte in (datos, datos[:-3]):
        try:
            recorte.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _leer_muestra_texto(ruta: Path, codificacion: str, n: int = 64 * 1024) -> str:
    with open(ruta, "r", encoding=codificacion, errors="replace", newline="") as f:
        return f.read(n)


def detectar_delimitador(muestra: str) -> str:
    try:
        return csv.Sniffer().sniff(muestra, delimiters=DELIMITADORES).delimiter
    except csv.Error:
        primera = muestra.splitlines()[0] if muestra else ""
        cuentas = {d: primera.count(d) for d in DELIMITADORES}
        mejor = max(cuentas, key=cuentas.get)
        return mejor if cuentas[mejor] > 0 else ","


def delimitador_consistente(muestra: str) -> str | None:
    """Para TXT: devuelve el delimitador si es consistente en las primeras líneas."""
    lineas = [l for l in muestra.splitlines()[:50] if l.strip()]
    if len(lineas) < 2:
        return None
    try:
        d = csv.Sniffer().sniff("\n".join(lineas), delimiters=DELIMITADORES).delimiter
    except csv.Error:
        return None
    cuentas = [len(next(csv.reader([l], delimiter=d))) for l in lineas]
    if cuentas[0] < 2:
        return None
    iguales = sum(1 for c in cuentas if c == cuentas[0])
    return d if iguales / len(cuentas) >= 0.9 else None


def estimar_filas(ruta: Path, codificacion: str) -> int:
    tamano = ruta.stat().st_size
    muestra = _leer_muestra_texto(ruta, codificacion, 256 * 1024)
    lineas = max(1, muestra.count("\n"))
    bytes_muestra = max(1, len(muestra.encode(codificacion, errors="replace")))
    return int(tamano / (bytes_muestra / lineas))


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Nombres de columna como texto limpio y únicos; filas totalmente vacías fuera."""
    df = df.copy()
    nombres, vistos = [], {}
    for i, c in enumerate(df.columns):
        n = str(c).strip() if c is not None and str(c).strip() else f"columna_{i + 1}"
        if n in vistos:
            vistos[n] += 1
            n = f"{n}_{vistos[n]}"
        else:
            vistos[n] = 1
        nombres.append(n)
    df.columns = nombres
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def validar(df: pd.DataFrame) -> Validacion:
    v = Validacion(filas=len(df), columnas=df.shape[1])
    if v.filas == 0:
        v.problemas.append(("err", "El fichero no tiene filas de datos."))
    if v.columnas == 0:
        v.problemas.append(("err", "El fichero no tiene columnas."))
    if v.filas == 0 or v.columnas == 0:
        return v
    for c in df.columns:
        serie = df[c]
        v.tipos[c] = str(serie.dtype)
        pct = float(serie.isna().mean())
        v.nulos_pct[c] = round(pct * 100, 2)
        if pct >= 1.0:
            v.problemas.append(("warn", f"La columna «{c}» está vacía."))
        elif pct > UMBRAL_NULOS_AVISO:
            v.problemas.append(("warn", f"La columna «{c}» tiene un {pct:.0%} de nulos."))
        if serie.nunique(dropna=True) <= 1 and v.filas > 1 and pct < 1.0:
            v.constantes.append(c)
        if str(c).lower().startswith("unnamed"):
            v.problemas.append(("warn", f"Columna sin nombre: «{c}»."))
    if v.constantes:
        v.problemas.append(("warn", "Columnas constantes: " + ", ".join(v.constantes) + "."))
    try:
        v.duplicados = int(df.duplicated().sum())
    except TypeError:
        v.duplicados = int(df.astype(str).duplicated().sum())
    if v.duplicados:
        v.problemas.append(("warn", f"{v.duplicados} filas duplicadas."))
    return v


# --- lectores -----------------------------------------------------------------------

def _leer_delimitado(ruta: Path, opciones: OpcionesImportacion, res: ResultadoFichero,
                     ctx: Contexto) -> pd.DataFrame:
    cod = opciones.codificacion or detectar_codificacion(ruta)
    delim = opciones.delimitador or detectar_delimitador(_leer_muestra_texto(ruta, cod))
    res.codificacion, res.delimitador = cod, delim
    tamano = ruta.stat().st_size
    comunes = dict(sep=delim, encoding=cod, header=opciones.fila_cabecera,
                   encoding_errors="strict", low_memory=False)
    if tamano > UMBRAL_MUESTREO_BYTES:
        res.muestreado = True
        res.avisos.append(f"Fichero de {tamano / 1024 ** 3:.1f} GB: se importa una muestra "
                          f"de {opciones.n_muestreo} filas ({opciones.muestreo}).")
        if opciones.muestreo == "aleatoria":
            return _muestreo_aleatorio(ruta, comunes, opciones, ctx, cod)
        return pd.read_csv(ruta, nrows=opciones.n_muestreo, **comunes)
    if tamano > UMBRAL_TROZOS_BYTES or estimar_filas(ruta, cod) > UMBRAL_TROZOS_FILAS:
        res.avisos.append("Fichero grande: lectura por trozos de 50.000 filas.")
        trozos = []
        for i, trozo in enumerate(pd.read_csv(ruta, chunksize=TAMANO_TROZO, **comunes)):
            ctx.comprobar()
            trozos.append(trozo)
            if i % 10 == 0:
                ctx.log(f"  {res.nombre}: {(i + 1) * TAMANO_TROZO:,} filas leídas")
        return pd.concat(trozos, ignore_index=True) if trozos else pd.DataFrame()
    try:
        return pd.read_csv(ruta, **comunes)
    except UnicodeDecodeError:
        if opciones.codificacion:
            raise
        res.codificacion = "latin-1"
        res.avisos.append(f"La codificación {cod} falló a mitad de fichero; se usa latin-1.")
        return pd.read_csv(ruta, **dict(comunes, encoding="latin-1"))


def _muestreo_aleatorio(ruta: Path, comunes: dict, opciones: OpcionesImportacion,
                        ctx: Contexto, cod: str) -> pd.DataFrame:
    total = max(1, estimar_filas(ruta, cod))
    fraccion = min(1.0, opciones.n_muestreo / total * 1.1)
    partes = []
    for i, trozo in enumerate(pd.read_csv(ruta, chunksize=TAMANO_TROZO, **comunes)):
        ctx.comprobar()
        partes.append(trozo.sample(frac=fraccion, random_state=opciones.semilla + i))
    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if len(df) > opciones.n_muestreo:
        df = df.sample(n=opciones.n_muestreo, random_state=opciones.semilla)
    return df.reset_index(drop=True)


def listar_hojas(ruta: str | Path) -> list[str]:
    return list(pd.ExcelFile(ruta).sheet_names)


def _leer_excel(ruta: Path, opciones: OpcionesImportacion, res: ResultadoFichero) -> pd.DataFrame:
    hojas = listar_hojas(ruta)
    res.hojas_disponibles = hojas
    if not hojas:
        raise ErrorImportacion("El libro no tiene hojas.")
    if opciones.hojas and opciones.hojas != ["*"]:
        elegidas = [h for h in opciones.hojas if h in hojas]
        faltan = [h for h in opciones.hojas if h not in hojas]
        if faltan:
            res.avisos.append("Hojas inexistentes: " + ", ".join(faltan) + ".")
        if not elegidas:
            raise ErrorImportacion("Ninguna de las hojas indicadas existe en el libro. "
                                   "Hojas disponibles: " + ", ".join(hojas) + ".")
    elif opciones.hojas == ["*"]:
        elegidas = hojas
    else:
        elegidas = hojas[:1]
        if len(hojas) > 1:
            res.avisos.append(f"El libro tiene {len(hojas)} hojas; se ha leído «{hojas[0]}».")
    tablas = pd.read_excel(ruta, sheet_name=elegidas, header=opciones.fila_cabecera)
    res.hoja = ", ".join(elegidas)
    if len(elegidas) == 1:
        return tablas[elegidas[0]]
    partes = []
    for h in elegidas:
        t = tablas[h].copy()
        t["hoja"] = h
        partes.append(t)
    return pd.concat(partes, ignore_index=True)


def _texto_libre(ruta: Path, codificacion: str) -> pd.DataFrame:
    with open(ruta, "r", encoding=codificacion, errors="replace") as f:
        lineas = [l.rstrip("\r\n") for l in f]
    lineas = [l for l in lineas if l.strip()]
    return pd.DataFrame({"texto": lineas, "origen": ruta.name})


def _leer_txt(ruta: Path, opciones: OpcionesImportacion, res: ResultadoFichero,
              ctx: Contexto) -> pd.DataFrame:
    cod = opciones.codificacion or detectar_codificacion(ruta)
    delim = opciones.delimitador or delimitador_consistente(_leer_muestra_texto(ruta, cod))
    if delim:
        o = OpcionesImportacion(**{**opciones.__dict__, "codificacion": cod, "delimitador": delim})
        return _leer_delimitado(ruta, o, res, ctx)
    res.codificacion, res.delimitador = cod, None
    res.avisos.append("Texto sin delimitador consistente: una fila por línea en «texto».")
    return _texto_libre(ruta, cod)


def _localizar_lista(obj: Any, ruta: str = "$") -> tuple[list, str]:
    """Busca la lista de objetos tabulable. Lanza ErrorNoTabulable con la ruta del nodo."""
    if isinstance(obj, list):
        if not obj:
            raise ErrorNoTabulable(ruta, "la lista está vacía")
        for i, el in enumerate(obj):
            if not isinstance(el, dict):
                raise ErrorNoTabulable(f"{ruta}[{i}]",
                                       f"se esperaba un objeto y hay {type(el).__name__}")
        return obj, ruta
    if isinstance(obj, dict):
        candidatas = [(k, v) for k, v in obj.items() if isinstance(v, list)]
        if not candidatas:
            anidados = [(k, v) for k, v in obj.items() if isinstance(v, dict)]
            for k, v in anidados:
                try:
                    return _localizar_lista(v, f"{ruta}.{k}")
                except ErrorNoTabulable:
                    continue
            raise ErrorNoTabulable(ruta, "el objeto no contiene ninguna lista de registros")
        ultimo_error: ErrorNoTabulable | None = None
        for k, v in candidatas:
            try:
                return _localizar_lista(v, f"{ruta}.{k}")
            except ErrorNoTabulable as e:
                ultimo_error = e
        assert ultimo_error is not None
        raise ultimo_error
    raise ErrorNoTabulable(ruta, f"el contenido es un {type(obj).__name__}")


def _leer_json(ruta: Path, opciones: OpcionesImportacion, res: ResultadoFichero) -> pd.DataFrame:
    cod = opciones.codificacion or detectar_codificacion(ruta)
    res.codificacion = cod
    if opciones.json_como_texto:
        res.avisos.append("JSON importado como texto (una fila por línea).")
        return _texto_libre(ruta, cod)
    with open(ruta, "r", encoding=cod) as f:
        contenido = f.read()
    try:
        obj = json.loads(contenido)
    except json.JSONDecodeError:
        registros = []
        for n, linea in enumerate(contenido.splitlines(), 1):
            if not linea.strip():
                continue
            try:
                registros.append(json.loads(linea))
            except json.JSONDecodeError as e:
                raise ErrorImportacion(f"JSON no válido (línea {n}): {e.msg}.") from e
        res.formato = "jsonl"
        lista, _ = _localizar_lista(registros)
        return pd.json_normalize(lista)
    lista, nodo = _localizar_lista(obj)
    if nodo != "$":
        res.avisos.append(f"Registros tomados del nodo {nodo}.")
    return pd.json_normalize(lista)


# --- importación ---------------------------------------------------------------------

def importar_fichero(ruta: str | Path, opciones: OpcionesImportacion | None = None,
                     ctx: Contexto | None = None) -> ResultadoFichero:
    opciones = opciones or OpcionesImportacion()
    ctx = ctx or Contexto()
    ruta = Path(ruta)
    res = ResultadoFichero(ruta=str(ruta))
    try:
        if not ruta.is_file():
            raise ErrorImportacion("El fichero no existe o no se puede leer.")
        formato = EXTENSIONES.get(ruta.suffix.lower())
        if not formato:
            raise ErrorImportacion(f"Formato no admitido ({ruta.suffix or 'sin extensión'}).")
        res.formato = formato
        res.tamano = ruta.stat().st_size
        if res.tamano == 0:
            raise ErrorImportacion("El fichero está vacío.")
        res.hash = hash_fichero(ruta)
        if formato == "csv":
            df = _leer_delimitado(ruta, opciones, res, ctx)
        elif formato == "excel":
            df = _leer_excel(ruta, opciones, res)
        elif formato == "txt":
            df = _leer_txt(ruta, opciones, res, ctx)
        else:
            df = _leer_json(ruta, opciones, res)
        df = normalizar(df)
        res.validacion = validar(df)
        res.df = df
        if res.validacion.bloquea:
            res.estado = "descartado"
            res.error = "; ".join(t for n, t in res.validacion.problemas if n == "err")
            res.df = None
        elif res.validacion.tiene_avisos or res.avisos:
            res.estado = "avisos"
        else:
            res.estado = "importado"
    except ErrorNoTabulable as e:
        res.estado, res.error, res.nodo_no_tabulable = "descartado", str(e), e.ruta_nodo
    except (ErrorImportacion, ValueError, UnicodeDecodeError, pd.errors.ParserError,
            OSError, KeyError) as e:
        res.estado, res.error = "descartado", f"{type(e).__name__}: {e}" if not isinstance(
            e, ErrorImportacion) else str(e)
    return res


def importar_lote(rutas: list[str | Path], opciones: OpcionesImportacion | None = None,
                  ctx: Contexto | None = None) -> ResumenLote:
    ctx = ctx or Contexto()
    ficheros = expandir_rutas(rutas)
    resumen = ResumenLote()
    total = max(1, len(ficheros))
    for i, ruta in enumerate(ficheros):
        ctx.comprobar()
        ctx.log(f"Importando {ruta.name} ({i + 1}/{len(ficheros)})")
        try:
            res = importar_fichero(ruta, opciones, ctx)
        except Cancelado:
            raise
        except Exception as e:  # noqa: BLE001 - un fichero nunca aborta el lote
            res = ResultadoFichero(ruta=str(ruta), error=f"Error inesperado: {e}")
        resumen.resultados.append(res)
        if res.estado == "descartado":
            ctx.log(f"  descartado: {res.error}")
        else:
            ctx.log(f"  {res.estado}: {res.filas} filas × {res.columnas} columnas")
            for a in res.avisos:
                ctx.log(f"  aviso: {a}")
        ctx.progreso((i + 1) * 100 / total)
    ctx.log(resumen.texto())
    return resumen


def comparar_esquemas(resultados: list[ResultadoFichero]) -> tuple[bool, dict]:
    """Compatibles si todos tienen el mismo conjunto de columnas.

    Devuelve (compatible, diferencias) con, por fichero, las columnas que le
    faltan y las que le sobran respecto a la unión.
    """
    validos = [r for r in resultados if r.df is not None]
    if len(validos) <= 1:
        return True, {}
    union: list[str] = []
    for r in validos:
        for c in r.df.columns:
            if c not in union:
                union.append(c)
    comunes = set(validos[0].df.columns)
    for r in validos[1:]:
        comunes &= set(r.df.columns)
    diferencias = {}
    for r in validos:
        cols = set(r.df.columns)
        faltan = [c for c in union if c not in cols]
        if faltan:
            diferencias[r.nombre] = {"faltan": faltan,
                                     "propias": [c for c in r.df.columns if c not in comunes]}
    return not diferencias, {"union": union, "comunes": [c for c in union if c in comunes],
                             "por_fichero": diferencias}


def combinar(resultados: list[ResultadoFichero], estrategia: str = "compatible") -> pd.DataFrame:
    """estrategia: compatible (exige mismo esquema) | union | interseccion."""
    validos = [r for r in resultados if r.df is not None]
    if not validos:
        raise ErrorImportacion("No hay ningún fichero válido que combinar.")
    compatible, dif = comparar_esquemas(validos)
    if estrategia == "compatible" and not compatible:
        raise ErrorImportacion("Los ficheros tienen esquemas distintos: elija unión o intersección.")
    if len(validos) == 1:
        return validos[0].df.copy()
    if estrategia == "interseccion" and not compatible:
        cols = dif["comunes"]
        if not cols:
            raise ErrorImportacion("Los ficheros no tienen ninguna columna en común.")
        partes = [r.df[cols] for r in validos]
    else:
        orden = dif.get("union") or list(validos[0].df.columns)
        partes = [r.df.reindex(columns=orden) for r in validos]
    return pd.concat(partes, ignore_index=True)


def resumen_columnas(df: pd.DataFrame) -> list[dict]:
    """Tabla de validación por columna para la UI."""
    v = validar(df)
    filas = []
    for c in df.columns:
        nulos = v.nulos_pct.get(c, 0.0)
        nivel = "ok"
        if nulos >= 100:
            nivel = "err"
        elif nulos > UMBRAL_NULOS_AVISO * 100 or c in v.constantes:
            nivel = "warn"
        filas.append({"columna": c, "tipo": v.tipos.get(c, ""), "nulos_pct": nulos,
                      "unicos": int(df[c].nunique(dropna=True)),
                      "constante": c in v.constantes, "nivel": nivel})
    return filas


def leer_csv_canonico(ruta: str | Path) -> pd.DataFrame:
    return pd.read_csv(ruta, encoding="utf-8", low_memory=False)


def guardar_csv_canonico(df: pd.DataFrame, ruta: str | Path) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False, encoding="utf-8")


__all__ = ["OpcionesImportacion", "ResultadoFichero", "ResumenLote", "Validacion",
           "importar_fichero", "importar_lote", "comparar_esquemas", "combinar", "validar",
           "hash_fichero", "hash_dataframe", "listar_hojas", "resumen_columnas",
           "ErrorImportacion", "ErrorNoTabulable"]
