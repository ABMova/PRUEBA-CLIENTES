"""Unico modulo que habla con la base de datos.

Ni la capa web ni la capa de negocio ejecutan SQL: todo pasa por aqui. Eso es
lo que permitiria migrar a PostgreSQL sustituyendo solo este fichero.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Iterable

from cryptography.fernet import Fernet, InvalidToken

import config

_local = threading.local()
_lock_escritura = threading.Lock()

ITERACIONES = 200000


# --------------------------------------------------------------- conexion --
def conexion() -> sqlite3.Connection:
    """Conexion por hilo, en modo WAL y con claves foraneas activas."""
    con = getattr(_local, "con", None)
    if con is None:
        config.preparar_carpetas()
        con = sqlite3.connect(config.RUTA_BD, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        _local.con = con
    return con


def cerrar_conexion() -> None:
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
        _local.con = None


def _consulta(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conexion().execute(sql, tuple(params)).fetchall()


def _uno(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conexion().execute(sql, tuple(params)).fetchone()


def _escribir(sql: str, params: Iterable[Any] = ()) -> int:
    """Devuelve el id de la fila insertada (0 si la sentencia no inserta)."""
    with _lock_escritura:
        con = conexion()
        cur = con.execute(sql, tuple(params))
        con.commit()
        return cur.lastrowid or 0


def _escribir_filas(sql: str, params: Iterable[Any] = ()) -> int:
    """Como _escribir, pero devuelve cuantas filas se han tocado."""
    with _lock_escritura:
        con = conexion()
        cur = con.execute(sql, tuple(params))
        con.commit()
        return cur.rowcount


# ------------------------------------------------------ esquema y migracion --
def aplicar_esquema(ruta_esquema=None) -> None:
    """Aplica el esquema de forma idempotente y anade columnas que falten."""
    ruta = ruta_esquema or config.RUTA_ESQUEMA
    with open(ruta, encoding="utf-8") as fichero:
        script = fichero.read()
    with _lock_escritura:
        con = conexion()
        con.executescript(script)
        con.commit()
    _migrar_columnas()


# Columnas anadidas despues de la primera version. Al arrancar se comprueba
# cuales faltan y se crean, para que actualizar no obligue a borrar datos.
_COLUMNAS_ESPERADAS: dict[str, dict[str, str]] = {
    "publicaciones": {
        "seccion": "TEXT NOT NULL DEFAULT ''",
        "sectores": "TEXT NOT NULL DEFAULT ''",
        "justificacion": "TEXT NOT NULL DEFAULT ''",
        "texto_incompleto": "INTEGER NOT NULL DEFAULT 0",
        "revision_manual": "INTEGER NOT NULL DEFAULT 0",
        "motivo_revision": "TEXT NOT NULL DEFAULT ''",
        "json_modelo": "TEXT NOT NULL DEFAULT ''",
        # v1.1: titulo resumido, fin de plazo y alertas
        "titulo_resumido": "TEXT NOT NULL DEFAULT ''",
        "plazo_fin": "TEXT",
        "plazo_fin_origen": "TEXT NOT NULL DEFAULT ''",
        "alerta_enviada": "INTEGER NOT NULL DEFAULT 0",
        # v1.9: a quien se dirige (privado | publico | personas | no_consta)
        "destinatario": "TEXT NOT NULL DEFAULT ''",
        # v1.18: plan estrategico o estrategia, que entra aunque no sea una ayuda
        "es_estrategia": "INTEGER NOT NULL DEFAULT 0",
    },
    "ejecuciones": {
        "llamadas_modelo": "INTEGER NOT NULL DEFAULT 0",
        "registro": "TEXT NOT NULL DEFAULT ''",
        "coste_usd": "REAL NOT NULL DEFAULT 0",
    },
    "boletines": {
        "via_acceso": "TEXT NOT NULL DEFAULT ''",
        "ultimo_estado": "TEXT NOT NULL DEFAULT 'pendiente'",
    },
}


def _migrar_columnas() -> None:
    con = conexion()
    for tabla, columnas in _COLUMNAS_ESPERADAS.items():
        existentes = {fila["name"] for fila in con.execute(f"PRAGMA table_info({tabla})")}
        if not existentes:
            continue
        for nombre, definicion in columnas.items():
            if nombre not in existentes:
                with _lock_escritura:
                    con.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")
                    con.commit()


def tablas() -> list[str]:
    filas = _consulta("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [fila["name"] for fila in filas]


# ------------------------------------------------------------------ cifrado --
def _clave_fernet() -> Fernet:
    config.preparar_carpetas()
    if not config.RUTA_CLAVE.exists():
        config.RUTA_CLAVE.write_bytes(Fernet.generate_key())
        try:
            os.chmod(config.RUTA_CLAVE, 0o600)
        except OSError:
            pass
    return Fernet(config.RUTA_CLAVE.read_bytes())


def cifrar(texto: str) -> str:
    if not texto:
        return ""
    return _clave_fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(texto: str) -> str:
    if not texto:
        return ""
    try:
        return _clave_fernet().decrypt(texto.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


# ------------------------------------------------------------------ ajustes --
def ajustes() -> dict[str, str]:
    return {fila["clave"]: fila["valor"] for fila in _consulta("SELECT clave, valor FROM ajustes")}


def ajuste(clave: str, defecto: str = "") -> str:
    fila = _uno("SELECT valor, cifrado FROM ajustes WHERE clave=?", (clave,))
    if fila is None:
        return defecto
    if fila["cifrado"]:
        return descifrar(fila["valor"]) or defecto
    return fila["valor"] or defecto


def ajuste_int(clave: str, defecto: int) -> int:
    try:
        return int(ajuste(clave, str(defecto)))
    except ValueError:
        return defecto


def guardar_ajuste(clave: str, valor: str) -> None:
    fila = _uno("SELECT cifrado FROM ajustes WHERE clave=?", (clave,))
    cifrado = bool(fila["cifrado"]) if fila else False
    almacenado = cifrar(valor) if cifrado else valor
    _escribir(
        "INSERT INTO ajustes (clave, valor, cifrado) VALUES (?,?,?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, actualizado_en=datetime('now')",
        (clave, almacenado, int(cifrado)),
    )


def ajuste_esta_definido(clave: str) -> bool:
    fila = _uno("SELECT valor FROM ajustes WHERE clave=?", (clave,))
    return bool(fila and fila["valor"])


# ----------------------------------------------------------------- usuarios --
def _hash_clave(clave: str, sal: str, iteraciones: int = ITERACIONES) -> str:
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), iteraciones)
    return base64.b64encode(derivada).decode("ascii")


def crear_usuario(usuario: str, clave: str, rol: str, nombre: str = "", correo: str = "",
                  cambio_obligatorio: bool = False) -> int:
    sal = secrets.token_bytes(16).hex()
    return _escribir(
        "INSERT INTO usuarios (usuario, nombre, correo, hash_clave, sal, iteraciones, rol, cambio_obligatorio) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (usuario.strip().lower(), nombre, correo, _hash_clave(clave, sal), sal, ITERACIONES, rol,
         int(cambio_obligatorio)),
    )


def usuario_por_nombre(usuario: str) -> sqlite3.Row | None:
    return _uno("SELECT * FROM usuarios WHERE usuario=?", (usuario.strip().lower(),))


def usuario_por_id(usuario_id: int) -> sqlite3.Row | None:
    return _uno("SELECT * FROM usuarios WHERE id=?", (usuario_id,))


def usuarios() -> list[sqlite3.Row]:
    return _consulta("SELECT * FROM usuarios ORDER BY usuario")


def verificar_clave(fila: sqlite3.Row, clave: str) -> bool:
    calculado = _hash_clave(clave, fila["sal"], fila["iteraciones"])
    return hmac.compare_digest(calculado, fila["hash_clave"])


def cambiar_clave(usuario_id: int, clave: str) -> None:
    sal = secrets.token_bytes(16).hex()
    _escribir(
        "UPDATE usuarios SET hash_clave=?, sal=?, iteraciones=?, cambio_obligatorio=0, "
        "actualizado_en=datetime('now') WHERE id=?",
        (_hash_clave(clave, sal), sal, ITERACIONES, usuario_id),
    )


def forzar_cambio_clave(usuario_id: int) -> None:
    _escribir("UPDATE usuarios SET cambio_obligatorio=1, actualizado_en=datetime('now') "
              "WHERE id=?", (usuario_id,))


def actualizar_usuario(usuario_id: int, nombre: str, correo: str, rol: str, activo: bool) -> None:
    _escribir(
        "UPDATE usuarios SET nombre=?, correo=?, rol=?, activo=?, actualizado_en=datetime('now') WHERE id=?",
        (nombre, correo, rol, int(activo), usuario_id),
    )


def administradores_activos(excluyendo: int | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM usuarios WHERE rol='administrador' AND activo=1"
    params: tuple[Any, ...] = ()
    if excluyendo is not None:
        sql += " AND id<>?"
        params = (excluyendo,)
    return int(_uno(sql, params)["n"])


def marcar_acceso(usuario_id: int) -> None:
    _escribir("UPDATE usuarios SET ultimo_acceso=datetime('now') WHERE id=?", (usuario_id,))


def asegurar_admin_inicial() -> str | None:
    """Crea el usuario admin la primera vez. Devuelve la clave provisional."""
    if _uno("SELECT id FROM usuarios LIMIT 1"):
        return None
    provisional = "MovaBoletines2026"
    crear_usuario("admin", provisional, "administrador", nombre="Administrador",
                  cambio_obligatorio=True)
    registrar_auditoria("sistema", "crear_usuario_inicial", "admin",
                        "Usuario inicial creado con clave provisional")
    return provisional


# ----------------------------------------------------------------- sesiones --
def crear_sesion(usuario_id: int, ip: str, agente: str, horas: int = 12) -> str:
    identificador = secrets.token_urlsafe(32)
    caduca = (datetime.utcnow() + timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
    _escribir(
        "INSERT INTO sesiones (id, usuario_id, ip, agente, caduca_en) VALUES (?,?,?,?,?)",
        (identificador, usuario_id, ip, agente[:250], caduca),
    )
    return identificador


def sesion_valida(identificador: str) -> sqlite3.Row | None:
    if not identificador:
        return None
    return _uno(
        "SELECT s.*, u.usuario, u.rol, u.activo, u.cambio_obligatorio, u.nombre "
        "FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
        "WHERE s.id=? AND s.caduca_en > datetime('now') AND u.activo=1",
        (identificador,),
    )


def cerrar_sesion(identificador: str) -> None:
    _escribir("DELETE FROM sesiones WHERE id=?", (identificador,))


def limpiar_sesiones_caducadas() -> None:
    _escribir("DELETE FROM sesiones WHERE caduca_en <= datetime('now')")


# ---------------------------------------------------------------- boletines --
def boletines(solo_activos: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM boletines"
    if solo_activos:
        sql += " WHERE activo=1"
    return _consulta(sql + " ORDER BY orden")


def boletin(codigo: str) -> sqlite3.Row | None:
    return _uno("SELECT * FROM boletines WHERE codigo=?", (codigo,))


def activar_boletin(codigo: str, activo: bool) -> None:
    _escribir("UPDATE boletines SET activo=?, actualizado_en=datetime('now') WHERE codigo=?",
              (int(activo), codigo))


def actualizar_estado_boletin(codigo: str, estado: str, resultado: str) -> None:
    _escribir(
        "UPDATE boletines SET ultimo_estado=?, ultimo_resultado=?, ultima_ejecucion=datetime('now'), "
        "actualizado_en=datetime('now') WHERE codigo=?",
        (estado, resultado[:500], codigo),
    )


# ----------------------------------------------------------- palabras clave --
def palabras_clave(solo_activas: bool = True, refuerzo: int | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM palabras_clave WHERE 1=1"
    params: list[Any] = []
    if solo_activas:
        sql += " AND activa=1"
    if refuerzo is not None:
        sql += " AND refuerzo=?"
        params.append(refuerzo)
    return _consulta(sql + " ORDER BY refuerzo, termino", params)


def anadir_palabra(termino: str, refuerzo: bool = False) -> None:
    _escribir("INSERT OR IGNORE INTO palabras_clave (termino, refuerzo) VALUES (?,?)",
              (termino.strip().lower(), int(refuerzo)))


def borrar_palabra(palabra_id: int) -> None:
    _escribir("DELETE FROM palabras_clave WHERE id=?", (palabra_id,))


def activar_palabra(palabra_id: int, activa: bool) -> None:
    _escribir("UPDATE palabras_clave SET activa=?, actualizado_en=datetime('now') WHERE id=?",
              (int(activa), palabra_id))


# ------------------------------------------------------------- destinatarios --
def destinatarios(solo_activos: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM destinatarios"
    if solo_activos:
        sql += " WHERE activo=1"
    return _consulta(sql + " ORDER BY correo")


def anadir_destinatario(correo: str, nombre: str = "") -> None:
    _escribir("INSERT OR IGNORE INTO destinatarios (correo, nombre) VALUES (?,?)",
              (correo.strip().lower(), nombre))


def activar_destinatario(destinatario_id: int, activo: bool) -> None:
    _escribir("UPDATE destinatarios SET activo=?, actualizado_en=datetime('now') WHERE id=?",
              (int(activo), destinatario_id))


def borrar_destinatario(destinatario_id: int) -> None:
    _escribir("DELETE FROM destinatarios WHERE id=?", (destinatario_id,))


# -------------------------------------------------------------- ejecuciones --
def crear_ejecucion(fecha_objetivo: str, tipo: str, lanzado_por: str) -> int:
    return _escribir(
        "INSERT INTO ejecuciones (fecha_objetivo, tipo, lanzado_por) VALUES (?,?,?)",
        (fecha_objetivo, tipo, lanzado_por),
    )


def cerrar_ejecucion(ejecucion_id: int, estado: str, detalle: str, registro: str,
                     contadores: dict[str, int]) -> None:
    _escribir(
        "UPDATE ejecuciones SET estado=?, detalle=?, registro=?, terminado_en=datetime('now'), "
        "boletines_ok=?, boletines_fallidos=?, publicaciones_brutas=?, candidatas=?, nuevas=?, "
        "alta_relevancia=?, llamadas_modelo=?, coste_usd=?, actualizado_en=datetime('now') "
        "WHERE id=?",
        (estado, detalle[:2000], registro[:100000],
         contadores.get("boletines_ok", 0), contadores.get("boletines_fallidos", 0),
         contadores.get("publicaciones_brutas", 0), contadores.get("candidatas", 0),
         contadores.get("nuevas", 0), contadores.get("alta_relevancia", 0),
         contadores.get("llamadas_modelo", 0), coste_de_ejecucion(ejecucion_id), ejecucion_id),
    )


def ejecuciones(limite: int = 50) -> list[sqlite3.Row]:
    return _consulta("SELECT * FROM ejecuciones ORDER BY id DESC LIMIT ?", (limite,))


def ejecucion(ejecucion_id: int) -> sqlite3.Row | None:
    return _uno("SELECT * FROM ejecuciones WHERE id=?", (ejecucion_id,))


def marcar_ejecuciones_interrumpidas() -> int:
    return _escribir_filas(
        "UPDATE ejecuciones SET estado='interrumpida', terminado_en=datetime('now'), "
        "detalle='La aplicacion se reinicio mientras la ejecucion estaba en curso', "
        "actualizado_en=datetime('now') WHERE estado='en_curso'"
    )


def ejecuciones_de_fecha(fecha_objetivo: str) -> list[sqlite3.Row]:
    return _consulta("SELECT id, tipo, estado, iniciado_en, boletines_ok FROM ejecuciones "
                     "WHERE fecha_objetivo=? ORDER BY id", (fecha_objetivo,))


def hay_ejecucion_en_curso() -> bool:
    return _uno("SELECT id FROM ejecuciones WHERE estado='en_curso' LIMIT 1") is not None


def registrar_scraping(ejecucion_id: int | None, codigo: str, fecha: str, estado: str,
                       recuperadas: int, intentos: int, duracion_ms: int, url: str,
                       detalle: str) -> None:
    _escribir(
        "INSERT INTO logs_scraping (ejecucion_id, codigo_boletin, fecha_objetivo, estado, "
        "recuperadas, intentos, duracion_ms, url, detalle) VALUES (?,?,?,?,?,?,?,?,?)",
        (ejecucion_id, codigo, fecha, estado, recuperadas, intentos, duracion_ms, url, detalle[:1000]),
    )


def boletines_sin_exito(fecha: str) -> list[str]:
    """Boletines que ese dia fallaron en TODAS las pasadas: ahi si se pierde algo."""
    filas = _consulta(
        "SELECT codigo_boletin FROM logs_scraping WHERE fecha_objetivo=? "
        "GROUP BY codigo_boletin "
        "HAVING SUM(CASE WHEN estado IN ('correcto','vacio') THEN 1 ELSE 0 END) = 0", (fecha,))
    return [fila["codigo_boletin"] for fila in filas]


def logs_scraping(ejecucion_id: int) -> list[sqlite3.Row]:
    return _consulta("SELECT * FROM logs_scraping WHERE ejecucion_id=? ORDER BY id", (ejecucion_id,))


# ------------------------------------------------------------ publicaciones --
def existe_hash(hash_contenido: str) -> bool:
    if _uno("SELECT id FROM publicaciones WHERE hash_contenido=?", (hash_contenido,)):
        return True
    return _uno("SELECT id FROM descartes WHERE hash_contenido=? AND activo=1",
                (hash_contenido,)) is not None


def titulos_recientes(dias: int) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT id, titulo_normalizado, codigo_boletin FROM publicaciones "
        "WHERE date(creado_en) >= date('now', ?) ", (f"-{int(dias)} day",))


# Guardadas solo para que su hash evite volver a pagar al modelo: no se envian
# ni se ven en el panel. "fuera_destinatario": para administraciones o personas.
ESTADOS_OCULTOS = ("no_convocatoria", "fuera_destinatario")
_SQL_VISIBLES = "estado NOT IN ('no_convocatoria', 'fuera_destinatario')"


def guardar_apartada(datos: dict[str, Any]) -> None:
    """Lo que el filtro previo deja fuera. Si ya estaba, no se duplica."""
    columnas = ("ejecucion_id", "codigo_boletin", "comunidad", "boletin_nombre",
                "fecha_publicacion", "titulo", "seccion", "organismo", "url_oficial",
                "url_pdf", "texto", "identificador", "motivo")
    _escribir(
        f"INSERT OR IGNORE INTO apartadas ({','.join(columnas)}) "
        f"VALUES ({','.join('?' for _ in columnas)})",
        [datos.get(col) if col != "texto" else (datos.get(col) or "")[:2000] for col in columnas])


def apartadas(dias: int = 15, limite: int = 500) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT * FROM apartadas WHERE date(fecha_publicacion) >= date('now', ?) "
        "ORDER BY fecha_publicacion DESC, codigo_boletin, id LIMIT ?",
        (f"-{int(dias)} day", limite))


def apartada(apartada_id: int) -> sqlite3.Row | None:
    return _uno("SELECT * FROM apartadas WHERE id=?", (apartada_id,))


def marcar_apartada(apartada_id: int, estado: str) -> None:
    _escribir("UPDATE apartadas SET estado=? WHERE id=?", (estado, apartada_id))


def publicaciones_ocultas(dias: int = 15, limite: int = 500) -> list[sqlite3.Row]:
    """Las que descarto la IA: no son convocatoria, o van a administraciones/personas."""
    return _consulta(
        "SELECT * FROM publicaciones WHERE estado IN ('no_convocatoria','fuera_destinatario') "
        "AND date(fecha_publicacion) >= date('now', ?) "
        "ORDER BY fecha_publicacion DESC, id DESC LIMIT ?", (f"-{int(dias)} day", limite))


def recuperar_publicacion(publicacion_id: int) -> None:
    """Saca del cajon una publicacion que la IA habia descartado."""
    _escribir("UPDATE publicaciones SET estado='nueva', actualizado_en=datetime('now') "
              "WHERE id=? AND estado IN ('no_convocatoria','fuera_destinatario')",
              (publicacion_id,))


def guardar_publicacion(datos: dict[str, Any]) -> int:
    columnas = [
        "ejecucion_id", "codigo_boletin", "comunidad", "boletin_nombre", "fecha_publicacion",
        "titulo", "titulo_resumido", "resumen", "organismo", "plazo", "plazo_fin",
        "plazo_fin_origen", "beneficiarios", "importe", "url_oficial",
        "url_pdf", "seccion", "relevancia", "sectores", "justificacion", "confianza",
        "motivo_confianza", "hash_contenido", "titulo_normalizado", "terminos", "contextos",
        "texto_incompleto", "revision_manual", "motivo_revision", "duplicado_de", "estado",
        "json_modelo", "destinatario", "es_estrategia",
    ]
    valores = [datos.get(col) for col in columnas]
    marcadores = ",".join("?" for _ in columnas)
    return _escribir(
        f"INSERT INTO publicaciones ({','.join(columnas)}) VALUES ({marcadores})", valores)


def publicaciones(filtros: dict[str, Any] | None = None, limite: int = 300) -> list[sqlite3.Row]:
    filtros = filtros or {}
    sql = "SELECT * FROM publicaciones WHERE 1=1"
    params: list[Any] = []
    if filtros.get("codigo_boletin"):
        sql += " AND codigo_boletin=?"
        params.append(filtros["codigo_boletin"])
    if filtros.get("relevancia"):
        sql += " AND relevancia=?"
        params.append(filtros["relevancia"])
    if filtros.get("fecha"):
        sql += " AND fecha_publicacion=?"
        params.append(filtros["fecha"])
    if filtros.get("desde"):
        sql += " AND fecha_publicacion>=?"
        params.append(filtros["desde"])
    if filtros.get("estado"):
        sql += " AND estado=?"
        params.append(filtros["estado"])
    else:
        # Las que el modelo descarto (no son convocatorias, o van a administraciones
        # o personas) se guardan solo para no volver a pagarlas: no se muestran.
        sql += " AND " + _SQL_VISIBLES
    if filtros.get("texto"):
        sql += " AND (titulo LIKE ? OR organismo LIKE ?)"
        patron = f"%{filtros['texto']}%"
        params.extend([patron, patron])
    sql += " ORDER BY fecha_publicacion DESC, id DESC LIMIT ?"
    params.append(limite)
    return _consulta(sql, params)


def publicacion(publicacion_id: int) -> sqlite3.Row | None:
    return _uno("SELECT * FROM publicaciones WHERE id=?", (publicacion_id,))


def publicaciones_de_ejecucion(ejecucion_id: int) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT * FROM publicaciones WHERE ejecucion_id=? AND estado IN ('nueva','enviada') "
        "ORDER BY comunidad, relevancia, id", (ejecucion_id,))


def publicaciones_por_ids(ids: list[int]) -> list[sqlite3.Row]:
    if not ids:
        return []
    marcadores = ",".join("?" for _ in ids)
    return _consulta(
        f"SELECT * FROM publicaciones WHERE id IN ({marcadores}) ORDER BY comunidad, id", ids)


def marcar_enviadas(ids: list[int]) -> None:
    if not ids:
        return
    marcadores = ",".join("?" for _ in ids)
    _escribir(
        f"UPDATE publicaciones SET estado='enviada', actualizado_en=datetime('now') "
        f"WHERE id IN ({marcadores}) AND estado='nueva'", ids)


# ------------------------------------------------------------------ descartes --
def descartar(publicacion_id: int, origen: str, destinatario: str = "", usuario: str = "",
              ip: str = "") -> bool:
    fila = publicacion(publicacion_id)
    if fila is None:
        return False
    _escribir(
        "INSERT INTO descartes (publicacion_id, hash_contenido, titulo, codigo_boletin, origen, "
        "destinatario, usuario, ip) VALUES (?,?,?,?,?,?,?,?)",
        (publicacion_id, fila["hash_contenido"], fila["titulo"], fila["codigo_boletin"], origen,
         destinatario, usuario, ip),
    )
    _escribir("UPDATE publicaciones SET estado='descartada', actualizado_en=datetime('now') WHERE id=?",
              (publicacion_id,))
    return True


def descartes(limite: int = 300) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT * FROM descartes WHERE activo=1 ORDER BY id DESC LIMIT ?", (limite,))


def recuperar_descarte(descarte_id: int) -> bool:
    fila = _uno("SELECT * FROM descartes WHERE id=?", (descarte_id,))
    if fila is None:
        return False
    _escribir("UPDATE descartes SET activo=0, actualizado_en=datetime('now') WHERE id=?", (descarte_id,))
    if fila["publicacion_id"]:
        _escribir("UPDATE publicaciones SET estado='nueva', actualizado_en=datetime('now') WHERE id=?",
                  (fila["publicacion_id"],))
    return True


# ----------------------------------------------------------- tokens descarte --
def crear_token_descarte(publicacion_id: int, destinatario: str, dias: int) -> str:
    token = secrets.token_urlsafe(24)[:32]
    caduca = (datetime.utcnow() + timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    _escribir(
        "INSERT INTO tokens_descarte (token, publicacion_id, destinatario, caduca_en) VALUES (?,?,?,?)",
        (token, publicacion_id, destinatario, caduca),
    )
    return token


def token_descarte(token: str) -> sqlite3.Row | None:
    return _uno("SELECT * FROM tokens_descarte WHERE token=?", (token,))


def consumir_token(token: str, ip: str) -> None:
    _escribir(
        "UPDATE tokens_descarte SET usado=1, usado_en=datetime('now'), ip_uso=?, "
        "actualizado_en=datetime('now') WHERE token=?", (ip, token))


# ---------------------------------------------------- limitacion por IP (WAF) --
def registrar_intento_ip(ip: str, recurso: str = "descarte") -> None:
    _escribir("INSERT INTO intentos_ip (ip, recurso) VALUES (?,?)", (ip, recurso))


def intentos_recientes(ip: str, minutos: int = 10, recurso: str = "descarte") -> int:
    fila = _uno(
        "SELECT COUNT(*) AS n FROM intentos_ip WHERE ip=? AND recurso=? "
        "AND creado_en > datetime('now', ?)", (ip, recurso, f"-{int(minutos)} minutes"))
    return int(fila["n"])


def limpiar_intentos_antiguos() -> None:
    _escribir("DELETE FROM intentos_ip WHERE creado_en < datetime('now', '-1 day')")


# -------------------------------------------------------------------- envios --
def registrar_envio(ejecucion_id: int | None, destinatarios_txt: str, asunto: str, estado: str,
                    intentos: int, detalle: str, publicaciones_n: int, ruta_html: str) -> int:
    return _escribir(
        "INSERT INTO envios (ejecucion_id, destinatarios, asunto, estado, intentos, detalle, "
        "publicaciones, ruta_html) VALUES (?,?,?,?,?,?,?,?)",
        (ejecucion_id, destinatarios_txt, asunto, estado, intentos, detalle[:1000], publicaciones_n,
         ruta_html),
    )


def envios(limite: int = 50) -> list[sqlite3.Row]:
    return _consulta("SELECT * FROM envios ORDER BY id DESC LIMIT ?", (limite,))


# ----------------------------------------------------------------- auditoria --
def registrar_auditoria(usuario: str, accion: str, objeto: str = "", detalle: str = "",
                        ip: str = "", resultado: str = "ok") -> None:
    _escribir(
        "INSERT INTO auditoria (usuario, accion, objeto, detalle, ip, resultado) VALUES (?,?,?,?,?,?)",
        (usuario, accion, objeto, detalle[:1000], ip, resultado),
    )


def auditoria(limite: int = 200) -> list[sqlite3.Row]:
    return _consulta("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limite,))


# ------------------------------------------------------------- panel / KPIs --
def kpis(fecha: str) -> dict[str, Any]:
    nuevas = _uno("SELECT COUNT(*) AS n FROM publicaciones WHERE fecha_publicacion=? "
                  "AND " + _SQL_VISIBLES, (fecha,))["n"]
    altas = _uno(
        "SELECT COUNT(*) AS n FROM publicaciones WHERE fecha_publicacion=? AND relevancia='alta' "
        "AND " + _SQL_VISIBLES, (fecha,))["n"]
    total = _uno("SELECT COUNT(*) AS n FROM publicaciones WHERE " + _SQL_VISIBLES)["n"]
    descartadas = _uno("SELECT COUNT(*) AS n FROM descartes WHERE activo=1")["n"]
    ultima = _uno("SELECT * FROM ejecuciones ORDER BY id DESC LIMIT 1")
    return {
        "nuevas_hoy": nuevas,
        "altas_hoy": altas,
        "historico": total,
        "descartadas": descartadas,
        "ultima_ejecucion": ultima,
        "gasto_mes_usd": gasto_mes_usd(),
    }


def exportar_publicaciones() -> list[dict[str, Any]]:
    """Historico completo sin credenciales ni hashes de usuario."""
    filas = _consulta(
        "SELECT id, codigo_boletin, comunidad, boletin_nombre, fecha_publicacion, titulo, "
        "titulo_resumido, resumen, organismo, plazo, plazo_fin, beneficiarios, importe, "
        "url_oficial, url_pdf, seccion, relevancia, "
        "sectores, justificacion, confianza, estado, revision_manual, creado_en "
        "FROM publicaciones WHERE " + _SQL_VISIBLES + " "
        "ORDER BY fecha_publicacion DESC, id DESC")
    return [dict(fila) for fila in filas]


def json_seguro(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False)


# ---------------------------------------------------------- consumo del modelo --
def registrar_consumo(ejecucion_id: int | None, fase: str, modelo: str, tokens_entrada: int,
                      tokens_salida: int, cache_lectura: int, cache_escritura: int,
                      coste_usd: float, resultado: str = "ok") -> None:
    _escribir(
        "INSERT INTO consumo_modelo (ejecucion_id, fase, modelo, tokens_entrada, tokens_salida, "
        "tokens_cache_lectura, tokens_cache_escritura, coste_usd, resultado) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (ejecucion_id, fase, modelo, tokens_entrada, tokens_salida, cache_lectura,
         cache_escritura, round(coste_usd, 6), resultado),
    )


def gasto_mes_usd(mes: str | None = None) -> float:
    """Gasto del mes natural (AAAA-MM, por defecto el actual) en dolares."""
    mes = mes or datetime.now().strftime("%Y-%m")
    fila = _uno("SELECT COALESCE(SUM(coste_usd), 0) AS total FROM consumo_modelo "
                "WHERE strftime('%Y-%m', creado_en, 'localtime') = ?", (mes,))
    return float(fila["total"])


def gasto_dia_usd(dia: str | None = None) -> float:
    dia = dia or datetime.now().strftime("%Y-%m-%d")
    fila = _uno("SELECT COALESCE(SUM(coste_usd), 0) AS total FROM consumo_modelo "
                "WHERE date(creado_en, 'localtime') = ?", (dia,))
    return float(fila["total"])


def coste_de_ejecucion(ejecucion_id: int) -> float:
    fila = _uno("SELECT COALESCE(SUM(coste_usd), 0) AS total FROM consumo_modelo "
                "WHERE ejecucion_id=?", (ejecucion_id,))
    return float(fila["total"])


def consumo_por_modelo(mes: str | None = None) -> list[sqlite3.Row]:
    mes = mes or datetime.now().strftime("%Y-%m")
    return _consulta(
        "SELECT modelo, fase, COUNT(*) AS llamadas, SUM(tokens_entrada) AS entrada, "
        "SUM(tokens_salida) AS salida, SUM(coste_usd) AS coste FROM consumo_modelo "
        "WHERE strftime('%Y-%m', creado_en, 'localtime') = ? "
        "GROUP BY modelo, fase ORDER BY coste DESC", (mes,))


def consumo_por_dia(dias: int = 30) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT date(creado_en, 'localtime') AS dia, COUNT(*) AS llamadas, "
        "SUM(tokens_entrada) AS entrada, SUM(tokens_salida) AS salida, SUM(coste_usd) AS coste "
        "FROM consumo_modelo WHERE date(creado_en, 'localtime') >= date('now', 'localtime', ?) "
        "GROUP BY dia ORDER BY dia DESC", (f"-{int(dias)} day",))


def consumo_por_mes(meses: int = 12) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT strftime('%Y-%m', creado_en, 'localtime') AS mes, COUNT(*) AS llamadas, "
        "SUM(tokens_entrada) AS entrada, SUM(tokens_salida) AS salida, SUM(coste_usd) AS coste "
        "FROM consumo_modelo GROUP BY mes ORDER BY mes DESC LIMIT ?", (meses,))


def ejecuciones_con_coste(limite: int = 30) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT e.id, e.fecha_objetivo, e.tipo, e.estado, e.nuevas, e.iniciado_en, "
        "COUNT(c.id) AS llamadas, COALESCE(SUM(c.tokens_entrada), 0) AS entrada, "
        "COALESCE(SUM(c.tokens_salida), 0) AS salida, COALESCE(SUM(c.coste_usd), 0) AS coste "
        "FROM ejecuciones e LEFT JOIN consumo_modelo c ON c.ejecucion_id = e.id "
        "GROUP BY e.id ORDER BY e.id DESC LIMIT ?", (limite,))


# ------------------------------------------------------- alertas y resumenes --
def pendientes_de_alerta(ids: list[int], hoy: str, limite: str) -> list[sqlite3.Row]:
    """Publicaciones de alta relevancia con fin de plazo entre hoy y limite, sin alertar."""
    if not ids:
        return []
    marcadores = ",".join("?" for _ in ids)
    return _consulta(
        f"SELECT * FROM publicaciones WHERE id IN ({marcadores}) AND relevancia='alta' "
        "AND alerta_enviada=0 AND plazo_fin IS NOT NULL AND plazo_fin >= ? AND plazo_fin <= ? "
        "AND estado IN ('nueva','enviada') ORDER BY plazo_fin", [*ids, hoy, limite])


def marcar_alertadas(ids: list[int]) -> None:
    if not ids:
        return
    marcadores = ",".join("?" for _ in ids)
    _escribir(f"UPDATE publicaciones SET alerta_enviada=1, actualizado_en=datetime('now') "
              f"WHERE id IN ({marcadores})", ids)


def publicaciones_entre(desde: str, hasta: str) -> list[sqlite3.Row]:
    """Publicaciones vivas (no descartadas) publicadas entre dos fechas ISO, ambas incluidas."""
    return _consulta(
        "SELECT * FROM publicaciones WHERE fecha_publicacion >= ? AND fecha_publicacion <= ? "
        "AND estado IN ('nueva','enviada') ORDER BY relevancia='alta' DESC, comunidad, id",
        (desde, hasta))


def plazos_que_vencen(desde: str, hasta: str) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT * FROM publicaciones WHERE plazo_fin IS NOT NULL AND plazo_fin >= ? "
        "AND plazo_fin <= ? AND estado IN ('nueva','enviada') "
        "ORDER BY plazo_fin, relevancia='alta' DESC", (desde, hasta))


# ------------------------------------------------ documentos de la publicacion --
def documento(publicacion_id: int) -> sqlite3.Row | None:
    return _uno("SELECT * FROM documentos_publicacion WHERE publicacion_id=?", (publicacion_id,))


def documentos_de(ids: list[int]) -> dict[int, str]:
    """Estado del documento de cada publicacion: {id: 'listo' | 'generando' | 'error'}."""
    if not ids:
        return {}
    marcadores = ",".join("?" for _ in ids)
    filas = _consulta(
        f"SELECT publicacion_id, estado FROM documentos_publicacion "
        f"WHERE publicacion_id IN ({marcadores})", ids)
    return {fila["publicacion_id"]: fila["estado"] for fila in filas}


def marcar_documento(publicacion_id: int, estado: str, usuario: str = "", error: str = "") -> None:
    _escribir(
        "INSERT INTO documentos_publicacion (publicacion_id, estado, solicitado_por, error) "
        "VALUES (?,?,?,?) ON CONFLICT(publicacion_id) DO UPDATE SET estado=excluded.estado, "
        "error=excluded.error, solicitado_por=CASE WHEN excluded.solicitado_por<>'' "
        "THEN excluded.solicitado_por ELSE solicitado_por END, actualizado_en=datetime('now')",
        (publicacion_id, estado, usuario, error[:1000]))


def guardar_documento(publicacion_id: int, datos_json: str, modelo: str, fuente: str,
                      paginas: int, caracteres: int, recortado: bool) -> None:
    _escribir(
        "UPDATE documentos_publicacion SET estado='listo', datos_json=?, modelo=?, fuente=?, "
        "paginas=?, caracteres=?, recortado=?, error='', actualizado_en=datetime('now') "
        "WHERE publicacion_id=?",
        (datos_json, modelo, fuente, paginas, caracteres, int(recortado), publicacion_id))


def documentos_generando_huerfanos() -> int:
    """Al arrancar: lo que quedo a medias por un reinicio vuelve a estar disponible."""
    return _escribir_filas(
        "UPDATE documentos_publicacion SET estado='error', "
        "error='La generacion se interrumpio al reiniciar la aplicacion. Vuelve a pulsar el boton.', "
        "actualizado_en=datetime('now') WHERE estado='generando'")


# ------------------------------------------ enlaces de documentos del correo --
def token_documento_para(publicacion_id: int, dias: int) -> str | None:
    """Enlace reutilizable de los documentos de una publicacion.

    Si ya tiene uno vigente con al menos una semana de margen se reutiliza (asi
    el correo diario, la alerta y el resumen semanal comparten enlace). Devuelve
    None si la publicacion no existe.
    """
    if publicacion(publicacion_id) is None:
        return None
    fila = _uno(
        "SELECT token FROM tokens_documento WHERE publicacion_id=? "
        "AND caduca_en > datetime('now', '+7 day') ORDER BY caduca_en DESC LIMIT 1",
        (publicacion_id,))
    if fila:
        return fila["token"]
    token = secrets.token_urlsafe(24)[:32]
    caduca = (datetime.utcnow() + timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    _escribir("INSERT INTO tokens_documento (token, publicacion_id, caduca_en) VALUES (?,?,?)",
              (token, publicacion_id, caduca))
    return token


def token_documento(token: str) -> sqlite3.Row | None:
    return _uno("SELECT * FROM tokens_documento WHERE token=?", (token,))


def usar_token_documento(token: str, ip: str) -> None:
    _escribir("UPDATE tokens_documento SET usos=usos+1, ultimo_uso=datetime('now'), ultima_ip=?, "
              "actualizado_en=datetime('now') WHERE token=?", (ip, token))


# ------------------------------------------------ lo hecho con el CRM de MOVA --
def registrar_crm(publicacion_id: int, accion: str, usuario: str, detalle: str = "") -> None:
    """Deja constancia de que el CRM dio de alta el programa o la tarea de una ayuda."""
    _escribir(
        "INSERT INTO crm_ejecuciones (publicacion_id, accion, usuario, detalle) VALUES (?,?,?,?) "
        "ON CONFLICT(publicacion_id, accion, usuario) DO UPDATE SET "
        "detalle=excluded.detalle, creado_en=datetime('now')",
        (publicacion_id, accion.strip().lower(), usuario.strip().lower(), detalle[:500]))


def crm_de_publicacion(publicacion_id: int) -> list[sqlite3.Row]:
    return _consulta(
        "SELECT accion, usuario, detalle, creado_en FROM crm_ejecuciones "
        "WHERE publicacion_id=? ORDER BY creado_en", (publicacion_id,))


def crm_de_publicaciones(ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    """Lo hecho en el CRM de varias publicaciones a la vez (para el correo y el panel)."""
    if not ids:
        return {}
    marcas = ",".join("?" for _ in ids)
    filas = _consulta(
        f"SELECT publicacion_id, accion, usuario, creado_en FROM crm_ejecuciones "
        f"WHERE publicacion_id IN ({marcas}) ORDER BY creado_en", tuple(ids))
    resultado: dict[int, list[sqlite3.Row]] = {}
    for fila in filas:
        resultado.setdefault(fila["publicacion_id"], []).append(fila)
    return resultado


def intentos_de_recurso(recurso: str, minutos: int) -> int:
    """Intentos de un recurso desde cualquier IP (p. ej. fallos de un mismo usuario)."""
    fila = _uno("SELECT COUNT(*) AS n FROM intentos_ip WHERE recurso=? "
                "AND creado_en > datetime('now', ?)", (recurso, f"-{int(minutos)} minutes"))
    return int(fila["n"])
