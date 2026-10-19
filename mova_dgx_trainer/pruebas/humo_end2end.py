"""Prueba de humo de punta a punta, sin interfaz.

Proyecto clasificacion_tabular con datos sintéticos: importación → preparación →
entrenamiento con entrenar_sklearn.py (en local) → evaluación → exportación, y
comprueba que existen el .docx y el .pdf.

Uso:  python pruebas/humo_end2end.py      (también lo recoge pytest)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from infra.cifrado import Cifrador  # noqa: E402
from infra.ejecutor_ssh import EjecutorLocal  # noqa: E402
from infra.rutas import Almacen  # noqa: E402
from nucleo.contexto import Contexto  # noqa: E402
from nucleo.coordinador import Coordinador  # noqa: E402
from nucleo.importador import OpcionesImportacion  # noqa: E402
from nucleo.preparador import ConfigPreparacion  # noqa: E402
from pruebas.recursos.generar import datos_clasificacion  # noqa: E402


def ejecutar(carpeta: Path, verbose: bool = True) -> dict:
    def decir(t):
        if verbose:
            print(t, flush=True)

    almacen = Almacen(carpeta / "almacen").crear()
    coord = Coordinador(almacen, Cifrador(almacen.config))
    coord.al_arrancar()
    ctx = Contexto(al_log=lambda t: None)

    origen = carpeta / "entrada"
    origen.mkdir(parents=True, exist_ok=True)
    df = datos_clasificacion(600)
    df.iloc[:300].to_csv(origen / "parte1.csv", index=False, sep=";")
    df.iloc[300:].to_excel(origen / "parte2.xlsx", index=False)

    pid = coord.crear_proyecto("Humo clasificación", "clasificacion_tabular", "prueba de humo")
    decir(f"[1] proyecto creado: id={pid}")

    imp = coord.importar(ctx, pid, [origen], OpcionesImportacion())
    assert imp["compatible"], imp["diferencias"]
    conf = coord.confirmar_importacion(pid)
    decir(f"[2] importación: {imp['resumen'].texto()} -> {conf['filas']} filas")
    assert conf["filas"] == 600

    prep = coord.preparar(ctx, pid, ConfigPreparacion(objetivo="compra"))
    decir(f"[3] preparación: {prep['division']['filas']} · baseline f1_macro="
          f"{prep['linea_base']['f1_macro']:.4f}")

    cfg = coord.guardar_configuracion(
        pid, "sklearn", {"modelo": "random_forest", "n_estimators": 60, "etapas": 3},
        coord.umbrales_por_defecto("clasificacion_tabular"), "f1_macro", 3, 42)
    res = coord.entrenar(ctx, pid, cfg, EjecutorLocal())
    decir(f"[4] entrenamiento: {res['ejecuciones']} ejecución(es), veredicto={res['veredicto']}")
    assert res["mejor_id"] is not None

    resumen = coord.resumen_resultados(pid)
    k = resumen["kpis"]
    decir(f"[5] evaluación: {k['metrica_nombre']}={k['metrica_valor']:.4f} · "
          f"mejora={k['mejora']:+.4f} · reintentos={k['reintentos']}")

    inf = coord.exportar_informe(ctx, pid)
    docx, pdf = Path(inf["docx"]), Path(inf["pdf"])
    assert docx.exists() and docx.stat().st_size > 0, docx
    assert pdf.exists() and pdf.stat().st_size > 0, pdf
    decir(f"[6] informe: {docx.name} ({docx.stat().st_size} B) y {pdf.name} ({pdf.stat().st_size} B)")
    return {"docx": docx, "pdf": pdf, "kpis": k}


def test_humo_end2end(tmp_path):
    r = ejecutar(tmp_path, verbose=False)
    assert r["docx"].exists() and r["pdf"].exists()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="humo_dgx_") as d:
        ejecutar(Path(d))
    print("HUMO END2END: OK")
