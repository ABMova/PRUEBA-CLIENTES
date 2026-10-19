"""Esquema de la base de datos SQLite, como lista de migraciones versionadas.

Cada migración es (versión, [sentencias]). Se aplican en orden y la versión
alcanzada se guarda en PRAGMA user_version. Las sentencias son idempotentes
(IF NOT EXISTS); las que no pueden serlo (ALTER TABLE) se protegen en
`migraciones.py` comprobando antes si la columna existe.

[PENDIENTE: confirmar SQLite] El uso de SQLite es una propuesta, no una petición.
"""

TABLAS = ("proyectos", "datasets", "ficheros_origen", "configuraciones",
          "ejecuciones", "metricas", "logs", "informes")

MIGRACION_1 = [
    """CREATE TABLE IF NOT EXISTS proyectos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        tipo_tarea TEXT NOT NULL,
        descripcion TEXT DEFAULT '',
        creado TEXT NOT NULL,
        actualizado TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ficheros_origen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        ruta TEXT NOT NULL,
        nombre TEXT NOT NULL,
        formato TEXT,
        tamano INTEGER,
        filas INTEGER,
        columnas INTEGER,
        hash TEXT,
        codificacion TEXT,
        delimitador TEXT,
        hoja TEXT,
        estado TEXT NOT NULL,
        avisos_json TEXT DEFAULT '[]',
        importado TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        fase TEXT NOT NULL,
        nombre TEXT,
        ruta TEXT NOT NULL,
        filas INTEGER,
        columnas INTEGER,
        hash TEXT,
        objetivo TEXT,
        division_json TEXT DEFAULT '{}',
        preparacion_json TEXT DEFAULT '{}',
        creado TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS configuraciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        framework TEXT NOT NULL,
        script TEXT NOT NULL,
        hiperparametros_json TEXT NOT NULL,
        umbrales_json TEXT NOT NULL,
        metrica_objetivo TEXT NOT NULL,
        max_reintentos INTEGER NOT NULL,
        semilla INTEGER NOT NULL,
        creado TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ejecuciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        configuracion_id INTEGER REFERENCES configuraciones(id),
        dataset_id INTEGER REFERENCES datasets(id),
        intento INTEGER NOT NULL DEFAULT 0,
        padre_id INTEGER REFERENCES ejecuciones(id),
        motivo TEXT DEFAULT '',
        estado TEXT NOT NULL,
        modo TEXT,
        comando TEXT,
        hiperparametros_json TEXT DEFAULT '{}',
        versiones_json TEXT DEFAULT '{}',
        curva_json TEXT DEFAULT '[]',
        ruta_modelo TEXT,
        ruta_log TEXT,
        duracion_s REAL,
        veredicto TEXT,
        detalle_veredicto_json TEXT DEFAULT '{}',
        error TEXT,
        iniciada TEXT NOT NULL,
        terminada TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS metricas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        dataset_id INTEGER REFERENCES datasets(id),
        ejecucion_id INTEGER REFERENCES ejecuciones(id),
        origen TEXT NOT NULL,
        conjunto TEXT NOT NULL,
        nombre TEXT NOT NULL,
        valor REAL,
        detalle_json TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
        ejecucion_id INTEGER REFERENCES ejecuciones(id),
        momento TEXT NOT NULL,
        nivel TEXT NOT NULL,
        texto TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS informes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        ruta_docx TEXT,
        ruta_pdf TEXT,
        hash_docx TEXT,
        hash_pdf TEXT,
        creado TEXT NOT NULL
    )""",
]

# v2: estado del pipeline persistido para reanudar, e índices de consulta.
MIGRACION_2 = [
    ("ADD_COLUMN", "proyectos", "estado_pipeline", "TEXT NOT NULL DEFAULT '{}'"),
    "CREATE INDEX IF NOT EXISTS ix_logs_ejecucion ON logs(ejecucion_id)",
    "CREATE INDEX IF NOT EXISTS ix_metricas_ejecucion ON metricas(ejecucion_id)",
    "CREATE INDEX IF NOT EXISTS ix_ejecuciones_proyecto ON ejecuciones(proyecto_id)",
]

MIGRACIONES = [
    (1, MIGRACION_1),
    (2, MIGRACION_2),
]

VERSION_ACTUAL = MIGRACIONES[-1][0]
