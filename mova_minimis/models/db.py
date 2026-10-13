"""Único módulo con SQL de la aplicación.

Cada llamada abre su propia conexión (las consultas corren en hilos aparte y
sqlite3 no comparte conexiones entre hilos). WAL permite leer el progreso
mientras el hilo de la consulta escribe.
"""
import json
import shutil
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

import config

# Columnas añadidas tras la v1.0: (tabla, columna, definición). Se crean si faltan.
COLUMNAS_POSTERIORES: list[tuple[str, str, str]] = []


def ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conectar(ruta: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(ruta or config.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")
    return con


@contextmanager
def conexion():
    con = _conectar()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _fila(r):
    return dict(r) if r is not None else None


def _filas(rs):
    return [dict(r) for r in rs]


# ---------------------------------------------------------------- migración
def inicializar() -> None:
    config.preparar_carpetas()
    esquema = (config.RAIZ_CODIGO / "models" / "schema.sql").read_text(encoding="utf-8")
    con = _conectar()
    try:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(esquema)
        for tabla, columna, definicion in COLUMNAS_POSTERIORES:
            existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}
            if columna not in existentes:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        con.commit()
    finally:
        con.close()


def comprobar_integridad(ruta: Path) -> tuple[bool, str]:
    try:
        con = sqlite3.connect(ruta)
        try:
            res = con.execute("PRAGMA integrity_check").fetchone()[0]
            tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return False, f"No es una base de datos SQLite válida: {e}"
    if res != "ok":
        return False, f"Comprobación de integridad fallida: {res}"
    faltan = {"usuarios", "consultas", "resultados_minimis", "auditoria"} - tablas
    if faltan:
        return False, "No es una copia de MOVA Minimis (faltan tablas: " + ", ".join(sorted(faltan)) + ")"
    return True, "ok"


# ---------------------------------------------------------------- ajustes
def leer_ajuste(clave: str, defecto=None):
    with conexion() as c:
        r = c.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
    return r["valor"] if r and r["valor"] is not None else defecto


def guardar_ajuste(clave: str, valor) -> None:
    with conexion() as c:
        c.execute(
            "INSERT INTO ajustes(clave, valor) VALUES(?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, fecha_actualizacion=?",
            (clave, valor, ahora_iso()),
        )


# ---------------------------------------------------------------- usuarios
def contar_usuarios() -> int:
    with conexion() as c:
        return c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]


def crear_usuario(email, nombre, contrasena_hash, rol, cambiar_clave=1) -> int:
    with conexion() as c:
        cur = c.execute(
            "INSERT INTO usuarios(email, nombre, contrasena_hash, rol, cambiar_clave) VALUES(?,?,?,?,?)",
            (email.strip().lower(), nombre.strip(), contrasena_hash, rol, cambiar_clave),
        )
        return cur.lastrowid


def usuario_por_email(email):
    with conexion() as c:
        return _fila(c.execute("SELECT * FROM usuarios WHERE email=?", (email.strip().lower(),)).fetchone())


def usuario_por_id(uid):
    with conexion() as c:
        return _fila(c.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone())


def listar_usuarios():
    with conexion() as c:
        return _filas(c.execute("SELECT * FROM usuarios ORDER BY activo DESC, nombre"))


def actualizar_usuario(uid, **campos) -> None:
    permitidos = {"nombre", "rol", "activo", "contrasena_hash", "cambiar_clave", "ultimo_acceso"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if not campos:
        return
    sets = ", ".join(f"{k}=?" for k in campos) + ", fecha_actualizacion=?"
    with conexion() as c:
        c.execute(f"UPDATE usuarios SET {sets} WHERE id=?", (*campos.values(), ahora_iso(), uid))


def contar_admins_activos() -> int:
    with conexion() as c:
        return c.execute("SELECT COUNT(*) FROM usuarios WHERE rol='admin' AND activo=1").fetchone()[0]


# ---------------------------------------------------------------- auditoría
def auditar(usuario_id, usuario_email, accion, entidad=None, detalle=None, ip=None) -> None:
    with conexion() as c:
        c.execute(
            "INSERT INTO auditoria(usuario_id, usuario_email, accion, entidad, detalle_json, ip_origen) "
            "VALUES(?,?,?,?,?,?)",
            (usuario_id, usuario_email, accion, entidad,
             json.dumps(detalle, ensure_ascii=False) if detalle is not None else None, ip),
        )


def listar_auditoria(limite=500, usuario_id=None, accion=None, texto=None):
    sql = "SELECT * FROM auditoria WHERE 1=1"
    params: list = []
    if usuario_id:
        sql += " AND usuario_id=?"
        params.append(usuario_id)
    if accion:
        sql += " AND accion=?"
        params.append(accion)
    if texto:
        sql += " AND (entidad LIKE ? OR detalle_json LIKE ? OR usuario_email LIKE ?)"
        params += [f"%{texto}%"] * 3
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    with conexion() as c:
        return _filas(c.execute(sql, params))


def acciones_auditadas():
    with conexion() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT accion FROM auditoria ORDER BY accion")]


# ---------------------------------------------------------------- consultas
def crear_consulta(cid, usuario_id, modo, fecha_ref, anos, clientes) -> None:
    with conexion() as c:
        c.execute(
            "INSERT INTO consultas(id, usuario_id, fecha_consulta, modo_periodo, fecha_referencia, "
            "anos_solicitados, clientes_buscados) VALUES(?,?,?,?,?,?,?)",
            (cid, usuario_id, ahora_iso(), modo, fecha_ref,
             json.dumps(anos), json.dumps(clientes, ensure_ascii=False)),
        )
        c.execute("INSERT INTO consultas_progreso(consulta_id, fase, porcentaje, mensaje) VALUES(?,?,?,?)",
                  (cid, "En cola", 0, "Consulta registrada"))


def consulta(cid):
    with conexion() as c:
        r = c.execute(
            "SELECT q.*, u.nombre AS usuario_nombre, u.email AS usuario_email "
            "FROM consultas q JOIN usuarios u ON u.id=q.usuario_id WHERE q.id=?", (cid,)).fetchone()
    return _fila(r)


def listar_consultas(limite=200, texto=None):
    sql = ("SELECT q.id, q.fecha_consulta, q.modo_periodo, q.fecha_referencia, q.anos_solicitados, "
           "q.estado, u.nombre AS usuario_nombre, "
           "(SELECT COUNT(*) FROM resultados_minimis r WHERE r.consulta_id=q.id) AS n_clientes, "
           "(SELECT group_concat(COALESCE(r.razon_social_bdns, r.razon_social, r.cif), ' · ') "
           "   FROM resultados_minimis r WHERE r.consulta_id=q.id) AS nombres "
           "FROM consultas q JOIN usuarios u ON u.id=q.usuario_id")
    params: list = []
    if texto:
        sql += (" WHERE q.id IN (SELECT consulta_id FROM resultados_minimis WHERE cif LIKE ? "
                "OR razon_social LIKE ? OR razon_social_bdns LIKE ?)")
        params += [f"%{texto}%"] * 3
    sql += " ORDER BY q.fecha_consulta DESC LIMIT ?"
    params.append(limite)
    with conexion() as c:
        return _filas(c.execute(sql, params))


def actualizar_consulta(cid, **campos) -> None:
    permitidos = {"estado", "mensaje_error", "informe_json", "clientes_buscados"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    sets = ", ".join(f"{k}=?" for k in campos) + ", fecha_actualizacion=?"
    with conexion() as c:
        c.execute(f"UPDATE consultas SET {sets} WHERE id=?", (*campos.values(), ahora_iso(), cid))


def marcar_interrumpidas() -> int:
    """Al arrancar: lo que estaba en curso murió con el proceso anterior."""
    with conexion() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM consultas WHERE estado='en_proceso'")]
        for cid in ids:
            c.execute("UPDATE consultas SET estado='interrumpida', mensaje_error=?, fecha_actualizacion=? "
                      "WHERE id=?", ("La aplicación se cerró durante la consulta. Reintentar.", ahora_iso(), cid))
            c.execute("UPDATE consultas_progreso SET fase='Interrumpida', mensaje=? WHERE consulta_id=?",
                      ("Interrumpida por reinicio de la aplicación, reintentar", cid))
        return len(ids)


def contar_consultas_por_estado():
    with conexion() as c:
        return {r[0]: r[1] for r in c.execute("SELECT estado, COUNT(*) FROM consultas GROUP BY estado")}


# ---------------------------------------------------------------- progreso y registro
def progreso(cid, fase, porcentaje, mensaje) -> None:
    with conexion() as c:
        c.execute("UPDATE consultas_progreso SET fase=?, porcentaje=?, mensaje=?, fecha_actualizacion=? "
                  "WHERE consulta_id=?", (fase, int(porcentaje), mensaje, ahora_iso(), cid))
        c.execute("INSERT INTO consultas_log(consulta_id, nivel, mensaje) VALUES(?,?,?)",
                  (cid, "info", f"[{fase}] {mensaje}"))


def registrar(cid, mensaje, nivel="info") -> None:
    with conexion() as c:
        c.execute("INSERT INTO consultas_log(consulta_id, nivel, mensaje) VALUES(?,?,?)", (cid, nivel, mensaje))


def leer_progreso(cid, desde_log=0):
    with conexion() as c:
        p = _fila(c.execute("SELECT * FROM consultas_progreso WHERE consulta_id=?", (cid,)).fetchone())
        log = _filas(c.execute("SELECT id, nivel, mensaje, fecha_creacion FROM consultas_log "
                               "WHERE consulta_id=? AND id>? ORDER BY id", (cid, desde_log)))
        est = c.execute("SELECT estado, mensaje_error FROM consultas WHERE id=?", (cid,)).fetchone()
    return p, log, (dict(est) if est else None)


def pedir_cancelacion(cid) -> None:
    with conexion() as c:
        c.execute("UPDATE consultas_progreso SET cancelar=1, fecha_actualizacion=? WHERE consulta_id=?",
                  (ahora_iso(), cid))


def cancelacion_pedida(cid) -> bool:
    with conexion() as c:
        r = c.execute("SELECT cancelar FROM consultas_progreso WHERE consulta_id=?", (cid,)).fetchone()
    return bool(r and r[0])


# ---------------------------------------------------------------- resultados
def borrar_resultados(cid) -> None:
    with conexion() as c:
        c.execute("DELETE FROM resultados_minimis WHERE consulta_id=?", (cid,))


def guardar_resultado(cid, calculo: dict, ayudas: list[dict]) -> int:
    with conexion() as c:
        cur = c.execute(
            "INSERT INTO resultados_minimis(consulta_id, cif, razon_social, razon_social_bdns, "
            "saldo_disponible, total_concedido_3anos, estado, detalles_json) VALUES(?,?,?,?,?,?,?,?)",
            (cid, calculo["cif"], calculo.get("razon_social"), calculo.get("razon_social_bdns"),
             calculo.get("saldo_disponible"), calculo.get("total_concedido_3anos"), calculo["estado"],
             json.dumps(calculo, ensure_ascii=False)),
        )
        rid = cur.lastrowid
        for a in ayudas:
            _insertar_ayuda(c, rid, a)
        return rid


def _insertar_ayuda(c, rid, a) -> int:
    cur = c.execute(
        "INSERT INTO ayudas_encontradas(resultado_id, origen, codigo_concesion, fecha_concesion, ano_fiscal, "
        "programa, numero_convocatoria, convocante, reglamento, clase_reglamento, instrumento, "
        "importe_concedido, fuente, url_referencia, fecha_publicacion, computa, usuario_id, notas) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, a.get("origen", "bdns"), a.get("codigo_concesion"), a.get("fecha_concesion"),
         a.get("ano_fiscal"), a.get("programa"), a.get("numero_convocatoria"), a.get("convocante"),
         a.get("reglamento"), a.get("clase_reglamento"), a.get("instrumento"),
         float(a.get("importe_concedido") or 0), a.get("fuente"), a.get("url_referencia"),
         a.get("fecha_publicacion"), 1 if a.get("computa") else 0, a.get("usuario_id"), a.get("notas")),
    )
    return cur.lastrowid


def actualizar_resultado(rid, calculo: dict, ayudas: list[dict]) -> None:
    """Sustituye el cálculo y las ayudas de un resultado (tras añadir o quitar una ayuda manual)."""
    with conexion() as c:
        c.execute("UPDATE resultados_minimis SET saldo_disponible=?, total_concedido_3anos=?, estado=?, "
                  "detalles_json=?, fecha_actualizacion=? WHERE id=?",
                  (calculo.get("saldo_disponible"), calculo.get("total_concedido_3anos"), calculo["estado"],
                   json.dumps(calculo, ensure_ascii=False), ahora_iso(), rid))
        c.execute("DELETE FROM ayudas_encontradas WHERE resultado_id=?", (rid,))
        for a in ayudas:
            _insertar_ayuda(c, rid, a)


def resultados_de(cid):
    with conexion() as c:
        res = _filas(c.execute("SELECT * FROM resultados_minimis WHERE consulta_id=? ORDER BY id", (cid,)))
        for r in res:
            r["detalles"] = json.loads(r.pop("detalles_json"))
            r["ayudas"] = _filas(c.execute(
                "SELECT * FROM ayudas_encontradas WHERE resultado_id=? ORDER BY fecha_concesion DESC, id",
                (r["id"],)))
    return res


def resultado(rid):
    with conexion() as c:
        r = _fila(c.execute("SELECT * FROM resultados_minimis WHERE id=?", (rid,)).fetchone())
        if r:
            r["detalles"] = json.loads(r.pop("detalles_json"))
            r["ayudas"] = _filas(c.execute("SELECT * FROM ayudas_encontradas WHERE resultado_id=? ORDER BY id",
                                           (rid,)))
    return r


# ---------------------------------------------------------------- documentos e informes
def registrar_documento(cid, nombre, tipo, ruta, hash_, tamano, metodo, usuario_id) -> int:
    with conexion() as c:
        cur = c.execute(
            "INSERT INTO documentos_procesados(consulta_id, nombre_original, tipo, ruta_almacenada, "
            "hash_contenido, tamano, metodo_extraccion, usuario_id) VALUES(?,?,?,?,?,?,?,?)",
            (cid, nombre, tipo, ruta, hash_, tamano, metodo, usuario_id))
        return cur.lastrowid


def asignar_documentos(ids, cid) -> None:
    with conexion() as c:
        for i in ids:
            c.execute("UPDATE documentos_procesados SET consulta_id=?, fecha_actualizacion=? WHERE id=?",
                      (cid, ahora_iso(), i))


def documentos_de(cid):
    with conexion() as c:
        return _filas(c.execute("SELECT * FROM documentos_procesados WHERE consulta_id=? ORDER BY id", (cid,)))


def registrar_informe(cid, formato, ruta, usuario_id) -> int:
    with conexion() as c:
        cur = c.execute("INSERT INTO informes_generados(consulta_id, formato, ruta_fichero, usuario_id) "
                        "VALUES(?,?,?,?)", (cid, formato, ruta, usuario_id))
        return cur.lastrowid


def informes_de(cid):
    with conexion() as c:
        return _filas(c.execute("SELECT * FROM informes_generados WHERE consulta_id=? ORDER BY id DESC", (cid,)))


# ---------------------------------------------------------------- caché BDNS
def leer_cache(clave, horas_validez):
    limite = (datetime.now(timezone.utc) - timedelta(hours=horas_validez)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conexion() as c:
        r = c.execute("SELECT respuesta_json FROM cache_bdns WHERE clave=? AND fecha_actualizacion>=?",
                      (clave, limite)).fetchone()
    return json.loads(r[0]) if r else None


def guardar_cache(clave, datos) -> None:
    with conexion() as c:
        c.execute("INSERT INTO cache_bdns(clave, respuesta_json) VALUES(?,?) "
                  "ON CONFLICT(clave) DO UPDATE SET respuesta_json=excluded.respuesta_json, "
                  "fecha_actualizacion=?", (clave, json.dumps(datos, ensure_ascii=False), ahora_iso()))


def vaciar_cache() -> int:
    with conexion() as c:
        return c.execute("DELETE FROM cache_bdns").rowcount


# ---------------------------------------------------------------- copias de seguridad
def copia_db(destino: Path) -> None:
    """Copia coherente aunque haya escrituras en curso (API de copia de SQLite)."""
    src = _conectar()
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def copia_automatica() -> Path:
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = config.DIR_BACKUPS / f"minimis_{marca}.db"
    copia_db(destino)
    copias = sorted(config.DIR_BACKUPS.glob("minimis_*.db"))
    for viejo in copias[:-config.COPIAS_A_CONSERVAR]:
        viejo.unlink(missing_ok=True)
    return destino


def listar_copias():
    return [{"nombre": p.name, "tamano": p.stat().st_size,
             "fecha": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")}
            for p in sorted(config.DIR_BACKUPS.glob("*.db"), reverse=True)]


def crear_zip_copia(destino: Path) -> Path:
    tmp = destino.with_suffix(".db.tmp")
    copia_db(tmp)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "minimis.db")
        for f in config.DIR_DOCUMENTOS.glob("*"):
            if f.is_file():
                z.write(f, f"documentos/{f.name}")
    tmp.unlink(missing_ok=True)
    return destino


def restaurar(origen_db: Path, documentos_zip: zipfile.ZipFile | None = None) -> Path:
    """Guarda copia del estado actual y vuelca la copia elegida sobre la base activa."""
    previa = config.DIR_BACKUPS / f"minimis_antes_de_restaurar_{datetime.now():%Y%m%d_%H%M%S}.db"
    copia_db(previa)
    src = sqlite3.connect(origen_db)
    dst = _conectar()
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    if documentos_zip is not None:
        for n in documentos_zip.namelist():
            if n.startswith("documentos/") and not n.endswith("/"):
                nombre = Path(n).name
                if nombre and ".." not in nombre:
                    with documentos_zip.open(n) as fi, open(config.DIR_DOCUMENTOS / nombre, "wb") as fo:
                        shutil.copyfileobj(fi, fo)
    inicializar()
    return previa
