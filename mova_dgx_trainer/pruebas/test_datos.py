import sqlite3

from datos import backup, migraciones
from datos.esquema import MIGRACION_1, TABLAS, VERSION_ACTUAL
from datos.repositorio import Repositorio
from infra.cifrado import Cifrador


def test_creacion_bd_nueva(tmp_path):
    repo = Repositorio(tmp_path / "bd" / "trainer.db")
    assert repo.version_esquema() == VERSION_ACTUAL
    with sqlite3.connect(repo.ruta) as c:
        tablas = {f[0] for f in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLAS) <= tablas
    pid = repo.crear_proyecto("demo", "clasificacion_tabular")
    assert repo.obtener_proyecto(pid)["estado_pipeline"]["paso_actual"] == "importacion"


def test_migracion_desde_v1_conserva_datos(tmp_path):
    ruta = tmp_path / "antigua.db"
    with sqlite3.connect(ruta) as c:
        for s in MIGRACION_1:
            c.execute(s)
        c.execute("PRAGMA user_version = 1")
        c.execute("INSERT INTO proyectos(nombre, tipo_tarea, creado, actualizado)"
                  " VALUES ('viejo','regresion_tabular','2026-01-01','2026-01-01')")
    repo = Repositorio(ruta)
    assert repo.migracion == (1, VERSION_ACTUAL)
    p = repo.listar_proyectos()[0]
    assert p["nombre"] == "viejo" and p["estado_pipeline"] == {}
    # idempotente: volver a aplicar no hace nada ni falla
    with sqlite3.connect(ruta) as c:
        assert migraciones.aplicar(c) == (VERSION_ACTUAL, VERSION_ACTUAL)


def test_ejecuciones_no_se_sobrescriben(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    pid = repo.crear_proyecto("p", "clasificacion_tabular")
    cid = repo.crear_configuracion(pid, "sklearn", "entrenar_sklearn.py", {}, {}, "f1_macro", 3, 42)
    did = repo.crear_dataset(pid, "preparado", "d", "x", 1, 1, "h")
    a = repo.crear_ejecucion(pid, cid, did, 0, None, "inicial", "local", {"batch_size": 64})
    b = repo.crear_ejecucion(pid, cid, did, 1, a, "oom_cuda", "local", {"batch_size": 32})
    assert a != b
    ej = repo.listar_ejecuciones(pid)
    assert [e["hiperparametros"]["batch_size"] for e in ej] == [64, 32]
    repo.guardar_metricas(pid, {"f1_macro": 0.8, "matriz_confusion": {"v": [[1]]}}, "modelo",
                          "test", ejecucion_id=b)
    m = repo.obtener_metricas("modelo", ejecucion_id=b)
    assert m["f1_macro"] == 0.8 and m["matriz_confusion"] == {"v": [[1]]}


def test_copias_rotan_y_restauran(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    repo.crear_proyecto("antes", "clasificacion_tabular")
    copia = backup.crear_copia(repo.ruta, tmp_path / "copias", maximo=3)
    repo.crear_proyecto("despues", "clasificacion_tabular")
    for _ in range(4):
        backup.crear_copia(repo.ruta, tmp_path / "copias", maximo=3)
    assert len(backup.listar(tmp_path / "copias")) == 3
    assert not copia.exists()  # rotada
    ultima = backup.listar(tmp_path / "copias")[-1]
    backup.restaurar(ultima, repo.ruta, tmp_path / "copias")
    assert len(repo.listar_proyectos()) == 2


def test_cifrado_ida_y_vuelta(tmp_path):
    c = Cifrador(tmp_path)
    c.guardar_json("conexion.enc", {"usuario": "mova_ia", "contrasena": "x"})
    assert b"mova_ia" not in (tmp_path / "conexion.enc").read_bytes()
    assert Cifrador(tmp_path).cargar_json("conexion.enc")["usuario"] == "mova_ia"
