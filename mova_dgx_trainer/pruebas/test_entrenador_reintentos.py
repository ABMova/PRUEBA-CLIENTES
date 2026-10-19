import json
import sys
from pathlib import Path

from infra.ejecutor_ssh import EjecutorLocal
from nucleo import entrenador, reintentos
from nucleo.contexto import Contexto


def test_parseo_linea_progreso():
    e = entrenador.parsear_linea('{"evento":"progreso","epoca":3,"total":20,"perdida":0.41,"metrica":0.78}')
    assert e == {"evento": "progreso", "epoca": 3, "total": 20, "perdida": 0.41, "metrica": 0.78}


def test_parseo_lineas_no_parseables_son_log():
    assert entrenador.parsear_linea("Warning: algo") == {"evento": "log", "texto": "Warning: algo"}
    assert entrenador.parsear_linea("{roto")["evento"] == "log"
    assert entrenador.parsear_linea('{"otro": 1}')["evento"] == "log"
    assert entrenador.parsear_linea('{"evento":"log","texto":"hola"}')["texto"] == "hola"


def test_reintento_ante_error_memoria_cuda():
    log = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB"
    ejec = {"estado": "error", "log": log, "error": "", "intento": 0, "motivo": "inicial",
            "hiperparametros": {"batch_size": 64, "epocas": 10}}
    d = reintentos.decidir("clasificacion_tabular", ejec, [ejec], 3)
    assert d.reintentar and d.motivo == reintentos.MOTIVO_OOM
    assert d.hiperparametros["batch_size"] == 32
    assert d.hiperparametros["epocas"] == 10
    assert ejec["hiperparametros"]["batch_size"] == 64  # no se modifica la anterior


def test_fallo_tecnico_un_solo_reintento_igual():
    ejec = {"estado": "error", "log": "ValueError", "intento": 0, "motivo": "inicial",
            "hiperparametros": {"modelo": "random_forest"}}
    d = reintentos.decidir("clasificacion_tabular", ejec, [ejec], 3)
    assert d.reintentar and d.hiperparametros == ejec["hiperparametros"]
    segundo = {**ejec, "intento": 1, "motivo": reintentos.MOTIVO_TECNICO}
    assert not reintentos.decidir("clasificacion_tabular", segundo, [ejec, segundo], 3).reintentar


def test_desempeno_recorre_rejilla_y_respeta_maximo():
    hist = []
    hp = {"modelo": "random_forest", "n_estimators": 200}
    for i in range(4):
        ejec = {"estado": "ok", "veredicto": "insuficiente", "intento": i,
                "motivo": "inicial" if i == 0 else reintentos.MOTIVO_DESEMPENO,
                "hiperparametros": hp}
        hist.append(ejec)
        d = reintentos.decidir("clasificacion_tabular", ejec, hist, 3)
        if i < 3:
            assert d.reintentar and d.hiperparametros != hp
            hp = d.hiperparametros
        else:
            assert not d.reintentar and d.motivo == "maximo"
    assert not reintentos.decidir("clasificacion_tabular", hist[0], hist[:1], 0).reintentar


def test_script_sklearn_contrato(tmp_path):
    """El script real escribe resultado.json con todas las claves y emite progreso JSONL."""
    from pruebas.recursos.generar import datos_clasificacion
    from nucleo.preparador import ConfigPreparacion, preparar
    from infra.rutas import carpeta_scripts

    r = preparar(datos_clasificacion(200), "clasificacion_tabular", ConfigPreparacion(objetivo="compra"))
    rutas = {}
    for n, d in (("train", r.train), ("val", r.val), ("test", r.test)):
        rutas[n] = tmp_path / f"o_{n}.csv"
        d.to_csv(rutas[n], index=False)
    config = entrenador.construir_config("clasificacion_tabular", r.especificacion,
                                         {"modelo": "random_forest", "n_estimators": 20, "etapas": 2},
                                         42, "f1_macro")
    carpeta = tmp_path / "e1"
    script = carpeta_scripts() / "entrenar_sklearn.py"
    entrenador.preparar_carpeta_trabajo(carpeta, config, rutas, script)
    eventos = []
    res = entrenador.lanzar(EjecutorLocal(sys.executable), carpeta, script.name,
                            Contexto(al_evento=eventos.append))
    assert res.estado == "ok", res.texto_log
    assert res.codigo_salida == 0
    datos = json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
    assert set(entrenador.CLAVES_RESULTADO) <= set(datos)
    assert [e["epoca"] for e in eventos] == [1, 2]
    assert (carpeta / "modelo.joblib").exists() and (carpeta / "predicciones_test.csv").exists()


def test_script_con_error_devuelve_codigo_distinto_de_cero(tmp_path):
    from infra.rutas import carpeta_scripts

    carpeta = tmp_path / "e2"
    carpeta.mkdir()
    (carpeta / "config.json").write_text(json.dumps({"tipo_tarea": "clasificacion_tabular",
                                                    "especificacion": {"objetivo": "y"},
                                                    "ficheros": {"train": "no.csv"}}), "utf-8")
    script = carpeta_scripts() / "entrenar_sklearn.py"
    (carpeta / script.name).write_bytes(script.read_bytes())
    res = entrenador.lanzar(EjecutorLocal(sys.executable), carpeta, script.name, Contexto())
    assert res.estado == "error" and res.codigo_salida != 0 and res.error
    assert Path(carpeta / "ejecucion.log").exists()
