-- MOVA Minimis · esquema completo, idempotente.
-- Se aplica entero en cada arranque. SQLite no admite "ADD COLUMN IF NOT EXISTS":
-- las columnas añadidas después de la v1.0 se declaran en models/db.py
-- (COLUMNAS_POSTERIORES) y se crean solo si faltan.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email               TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nombre              TEXT NOT NULL,
    contrasena_hash     TEXT NOT NULL,
    rol                 TEXT NOT NULL CHECK (rol IN ('admin','consultor','viewer')),
    activo              INTEGER NOT NULL DEFAULT 1,
    cambiar_clave       INTEGER NOT NULL DEFAULT 1,
    ultimo_acceso       TEXT,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS ajustes (
    clave               TEXT PRIMARY KEY,
    valor               TEXT,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS consultas (
    id                  TEXT PRIMARY KEY,               -- uuid
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    fecha_consulta      TEXT NOT NULL,
    modo_periodo        TEXT NOT NULL CHECK (modo_periodo IN ('movil','ejercicios')),
    fecha_referencia    TEXT NOT NULL,                  -- AAAA-MM-DD
    anos_solicitados    TEXT NOT NULL,                  -- JSON
    clientes_buscados   TEXT NOT NULL,                  -- JSON (salida del Parser)
    estado              TEXT NOT NULL DEFAULT 'en_proceso'
                        CHECK (estado IN ('en_proceso','completada','error','cancelada','interrumpida')),
    mensaje_error       TEXT,
    informe_json        TEXT,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_consultas_usuario ON consultas(usuario_id);
CREATE INDEX IF NOT EXISTS ix_consultas_fecha   ON consultas(fecha_consulta);

CREATE TABLE IF NOT EXISTS consultas_progreso (
    consulta_id         TEXT PRIMARY KEY REFERENCES consultas(id) ON DELETE CASCADE,
    fase                TEXT NOT NULL,
    porcentaje          INTEGER NOT NULL DEFAULT 0,
    mensaje             TEXT,
    cancelar            INTEGER NOT NULL DEFAULT 0,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS consultas_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id         TEXT NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
    nivel               TEXT NOT NULL DEFAULT 'info',
    mensaje             TEXT NOT NULL,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_log_consulta ON consultas_log(consulta_id);

CREATE TABLE IF NOT EXISTS resultados_minimis (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id           TEXT NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
    cif                   TEXT NOT NULL,
    razon_social          TEXT,
    razon_social_bdns     TEXT,
    saldo_disponible      REAL,
    total_concedido_3anos REAL,
    estado                TEXT NOT NULL
                          CHECK (estado IN ('SALDO_DISPONIBLE','LIMITE_ALCANZADO','LIMITE_SUPERADO','PENDIENTE')),
    detalles_json         TEXT NOT NULL,
    fecha_creacion        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_resultados_consulta ON resultados_minimis(consulta_id);
CREATE INDEX IF NOT EXISTS ix_resultados_cif      ON resultados_minimis(cif);

CREATE TABLE IF NOT EXISTS ayudas_encontradas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    resultado_id        INTEGER NOT NULL REFERENCES resultados_minimis(id) ON DELETE CASCADE,
    origen              TEXT NOT NULL DEFAULT 'bdns' CHECK (origen IN ('bdns','manual')),
    codigo_concesion    TEXT,
    fecha_concesion     TEXT,                           -- AAAA-MM-DD
    ano_fiscal          INTEGER,
    programa            TEXT,                           -- título de la convocatoria
    numero_convocatoria TEXT,
    convocante          TEXT,
    reglamento          TEXT,
    clase_reglamento    TEXT,                           -- general | agricola | pesca | sieg | otro
    instrumento         TEXT,
    importe_concedido   REAL NOT NULL DEFAULT 0,        -- ayuda equivalente
    fuente              TEXT,
    url_referencia      TEXT,
    fecha_publicacion   TEXT,                           -- fecha de registro en la BDNS
    computa             INTEGER NOT NULL DEFAULT 0,     -- 1 si entra en el periodo de cálculo
    usuario_id          INTEGER REFERENCES usuarios(id),
    notas               TEXT,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_ayudas_resultado ON ayudas_encontradas(resultado_id);

CREATE TABLE IF NOT EXISTS documentos_procesados (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id         TEXT REFERENCES consultas(id) ON DELETE SET NULL,
    nombre_original     TEXT NOT NULL,
    tipo                TEXT NOT NULL,
    ruta_almacenada     TEXT NOT NULL,
    hash_contenido      TEXT NOT NULL,
    tamano              INTEGER,
    metodo_extraccion   TEXT,
    usuario_id          INTEGER REFERENCES usuarios(id),
    fecha_subida        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_documentos_consulta ON documentos_procesados(consulta_id);

CREATE TABLE IF NOT EXISTS informes_generados (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id         TEXT NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
    formato             TEXT NOT NULL CHECK (formato IN ('docx','pdf','xlsx','json')),
    ruta_fichero        TEXT NOT NULL,
    usuario_id          INTEGER REFERENCES usuarios(id),
    fecha_generacion    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_informes_consulta ON informes_generados(consulta_id);

CREATE TABLE IF NOT EXISTS auditoria (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id          INTEGER REFERENCES usuarios(id),
    usuario_email       TEXT,
    accion              TEXT NOT NULL,
    entidad             TEXT,
    detalle_json        TEXT,
    ip_origen           TEXT,
    timestamp           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_auditoria_usuario ON auditoria(usuario_id);
CREATE INDEX IF NOT EXISTS ix_auditoria_fecha   ON auditoria(timestamp);

-- Caché de respuestas de la BDNS: evita consultar dos veces el mismo CIF en poco tiempo
CREATE TABLE IF NOT EXISTS cache_bdns (
    clave               TEXT PRIMARY KEY,               -- p. ej. 'minimis:B12345678' o 'conv:866005'
    respuesta_json      TEXT NOT NULL,
    fecha_creacion      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
