-- MOVA Boletines Oficiales - esquema completo e idempotente.
-- Se aplica en cada arranque. Nunca borra datos: solo crea lo que falte.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario            TEXT NOT NULL UNIQUE,
    nombre             TEXT NOT NULL DEFAULT '',
    correo             TEXT NOT NULL DEFAULT '',
    hash_clave         TEXT NOT NULL,
    sal                TEXT NOT NULL,
    iteraciones        INTEGER NOT NULL DEFAULT 200000,
    rol                TEXT NOT NULL DEFAULT 'consulta',
    activo             INTEGER NOT NULL DEFAULT 1,
    cambio_obligatorio INTEGER NOT NULL DEFAULT 0,
    ultimo_acceso      TEXT,
    creado_en          TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_usuarios_rol ON usuarios(rol, activo);

CREATE TABLE IF NOT EXISTS sesiones (
    id             TEXT PRIMARY KEY,
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    ip             TEXT NOT NULL DEFAULT '',
    agente         TEXT NOT NULL DEFAULT '',
    caduca_en      TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_sesiones_usuario ON sesiones(usuario_id);
CREATE INDEX IF NOT EXISTS ix_sesiones_caduca ON sesiones(caduca_en);

CREATE TABLE IF NOT EXISTS boletines (
    codigo           TEXT PRIMARY KEY,
    nombre           TEXT NOT NULL,
    comunidad        TEXT NOT NULL,
    url_base         TEXT NOT NULL DEFAULT '',
    via_acceso       TEXT NOT NULL DEFAULT '',
    activo           INTEGER NOT NULL DEFAULT 1,
    orden            INTEGER NOT NULL DEFAULT 0,
    ultimo_resultado TEXT NOT NULL DEFAULT '',
    ultimo_estado    TEXT NOT NULL DEFAULT 'pendiente',
    ultima_ejecucion TEXT,
    creado_en        TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS palabras_clave (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    termino        TEXT NOT NULL UNIQUE,
    activa         INTEGER NOT NULL DEFAULT 1,
    refuerzo       INTEGER NOT NULL DEFAULT 0,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ejecuciones (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_objetivo       TEXT NOT NULL,
    tipo                 TEXT NOT NULL DEFAULT 'programada',
    estado               TEXT NOT NULL DEFAULT 'en_curso',
    iniciado_en          TEXT NOT NULL DEFAULT (datetime('now')),
    terminado_en         TEXT,
    lanzado_por          TEXT NOT NULL DEFAULT 'planificador',
    boletines_ok         INTEGER NOT NULL DEFAULT 0,
    boletines_fallidos   INTEGER NOT NULL DEFAULT 0,
    publicaciones_brutas INTEGER NOT NULL DEFAULT 0,
    candidatas           INTEGER NOT NULL DEFAULT 0,
    nuevas               INTEGER NOT NULL DEFAULT 0,
    alta_relevancia      INTEGER NOT NULL DEFAULT 0,
    llamadas_modelo      INTEGER NOT NULL DEFAULT 0,
    coste_usd            REAL NOT NULL DEFAULT 0,
    detalle              TEXT NOT NULL DEFAULT '',
    registro             TEXT NOT NULL DEFAULT '',
    creado_en            TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_ejecuciones_fecha ON ejecuciones(fecha_objetivo);
CREATE INDEX IF NOT EXISTS ix_ejecuciones_estado ON ejecuciones(estado);

CREATE TABLE IF NOT EXISTS logs_scraping (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecucion_id   INTEGER REFERENCES ejecuciones(id) ON DELETE CASCADE,
    codigo_boletin TEXT NOT NULL,
    fecha_objetivo TEXT NOT NULL,
    estado         TEXT NOT NULL,
    recuperadas    INTEGER NOT NULL DEFAULT 0,
    intentos       INTEGER NOT NULL DEFAULT 1,
    duracion_ms    INTEGER NOT NULL DEFAULT 0,
    url            TEXT NOT NULL DEFAULT '',
    detalle        TEXT NOT NULL DEFAULT '',
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_logs_ejecucion ON logs_scraping(ejecucion_id);
CREATE INDEX IF NOT EXISTS ix_logs_boletin ON logs_scraping(codigo_boletin, fecha_objetivo);

CREATE TABLE IF NOT EXISTS publicaciones (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecucion_id       INTEGER REFERENCES ejecuciones(id) ON DELETE SET NULL,
    codigo_boletin     TEXT NOT NULL REFERENCES boletines(codigo),
    comunidad          TEXT NOT NULL DEFAULT '',
    boletin_nombre     TEXT NOT NULL DEFAULT '',
    fecha_publicacion  TEXT NOT NULL,
    titulo             TEXT NOT NULL,
    titulo_resumido    TEXT NOT NULL DEFAULT '',
    resumen            TEXT NOT NULL DEFAULT '',
    organismo          TEXT NOT NULL DEFAULT '',
    plazo              TEXT NOT NULL DEFAULT '',
    plazo_fin          TEXT,
    plazo_fin_origen   TEXT NOT NULL DEFAULT '',
    alerta_enviada     INTEGER NOT NULL DEFAULT 0,
    beneficiarios      TEXT NOT NULL DEFAULT '',
    importe            TEXT NOT NULL DEFAULT '',
    url_oficial        TEXT NOT NULL DEFAULT '',
    url_pdf            TEXT NOT NULL DEFAULT '',
    seccion            TEXT NOT NULL DEFAULT '',
    relevancia         TEXT NOT NULL DEFAULT 'media',
    sectores           TEXT NOT NULL DEFAULT '',
    justificacion      TEXT NOT NULL DEFAULT '',
    confianza          TEXT NOT NULL DEFAULT '',
    motivo_confianza   TEXT NOT NULL DEFAULT '',
    hash_contenido     TEXT NOT NULL UNIQUE,
    titulo_normalizado TEXT NOT NULL DEFAULT '',
    terminos           TEXT NOT NULL DEFAULT '',
    contextos          TEXT NOT NULL DEFAULT '',
    texto_incompleto   INTEGER NOT NULL DEFAULT 0,
    revision_manual    INTEGER NOT NULL DEFAULT 0,
    motivo_revision    TEXT NOT NULL DEFAULT '',
    duplicado_de       INTEGER REFERENCES publicaciones(id) ON DELETE SET NULL,
    estado             TEXT NOT NULL DEFAULT 'nueva',
    json_modelo        TEXT NOT NULL DEFAULT '',
    creado_en          TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_pub_hash ON publicaciones(hash_contenido);
CREATE INDEX IF NOT EXISTS ix_pub_fecha ON publicaciones(fecha_publicacion);
CREATE INDEX IF NOT EXISTS ix_pub_boletin ON publicaciones(codigo_boletin, fecha_publicacion);
CREATE INDEX IF NOT EXISTS ix_pub_estado ON publicaciones(estado, relevancia);

-- Cada llamada al modelo, con sus tokens y su coste. Alimenta el panel de
-- coste y el tope de gasto mensual.
CREATE TABLE IF NOT EXISTS consumo_modelo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecucion_id        INTEGER REFERENCES ejecuciones(id) ON DELETE SET NULL,
    fase                TEXT NOT NULL DEFAULT '',
    modelo              TEXT NOT NULL,
    tokens_entrada      INTEGER NOT NULL DEFAULT 0,
    tokens_salida       INTEGER NOT NULL DEFAULT 0,
    tokens_cache_lectura  INTEGER NOT NULL DEFAULT 0,
    tokens_cache_escritura INTEGER NOT NULL DEFAULT 0,
    coste_usd           REAL NOT NULL DEFAULT 0,
    resultado           TEXT NOT NULL DEFAULT 'ok',
    creado_en           TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_consumo_fecha ON consumo_modelo(creado_en);
CREATE INDEX IF NOT EXISTS ix_consumo_ejecucion ON consumo_modelo(ejecucion_id);

CREATE TABLE IF NOT EXISTS descartes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    publicacion_id INTEGER REFERENCES publicaciones(id) ON DELETE SET NULL,
    hash_contenido TEXT NOT NULL,
    titulo         TEXT NOT NULL DEFAULT '',
    codigo_boletin TEXT NOT NULL DEFAULT '',
    origen         TEXT NOT NULL DEFAULT 'correo',
    destinatario   TEXT NOT NULL DEFAULT '',
    usuario        TEXT NOT NULL DEFAULT '',
    ip             TEXT NOT NULL DEFAULT '',
    activo         INTEGER NOT NULL DEFAULT 1,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_descartes_hash ON descartes(hash_contenido, activo);

CREATE TABLE IF NOT EXISTS tokens_descarte (
    token          TEXT PRIMARY KEY,
    publicacion_id INTEGER NOT NULL REFERENCES publicaciones(id) ON DELETE CASCADE,
    destinatario   TEXT NOT NULL DEFAULT '',
    usado          INTEGER NOT NULL DEFAULT 0,
    usado_en       TEXT,
    ip_uso         TEXT NOT NULL DEFAULT '',
    caduca_en      TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_tokens_pub ON tokens_descarte(publicacion_id);

CREATE TABLE IF NOT EXISTS destinatarios (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    correo         TEXT NOT NULL UNIQUE,
    nombre         TEXT NOT NULL DEFAULT '',
    activo         INTEGER NOT NULL DEFAULT 1,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS envios (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecucion_id   INTEGER REFERENCES ejecuciones(id) ON DELETE SET NULL,
    destinatarios  TEXT NOT NULL DEFAULT '',
    asunto         TEXT NOT NULL DEFAULT '',
    estado         TEXT NOT NULL DEFAULT 'pendiente',
    intentos       INTEGER NOT NULL DEFAULT 0,
    detalle        TEXT NOT NULL DEFAULT '',
    publicaciones  INTEGER NOT NULL DEFAULT 0,
    ruta_html      TEXT NOT NULL DEFAULT '',
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_envios_ejecucion ON envios(ejecucion_id);

CREATE TABLE IF NOT EXISTS ajustes (
    clave          TEXT PRIMARY KEY,
    valor          TEXT NOT NULL DEFAULT '',
    cifrado        INTEGER NOT NULL DEFAULT 0,
    descripcion    TEXT NOT NULL DEFAULT '',
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auditoria (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario        TEXT NOT NULL DEFAULT 'sistema',
    accion         TEXT NOT NULL,
    objeto         TEXT NOT NULL DEFAULT '',
    detalle        TEXT NOT NULL DEFAULT '',
    ip             TEXT NOT NULL DEFAULT '',
    resultado      TEXT NOT NULL DEFAULT 'ok',
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_auditoria_fecha ON auditoria(creado_en);

CREATE TABLE IF NOT EXISTS intentos_ip (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ip             TEXT NOT NULL,
    recurso        TEXT NOT NULL DEFAULT 'descarte',
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_intentos_ip ON intentos_ip(ip, recurso, creado_en);

-- ---------------------------------------------------------------- semillas --

INSERT OR IGNORE INTO boletines (codigo, nombre, comunidad, url_base, via_acceso, orden) VALUES
 ('DOGV',  'Diari Oficial de la Generalitat Valenciana',   'Comunidad Valenciana', 'https://dogv.gva.es',                  'API REST JSON (dogv-portal)',     1),
 ('BOCM',  'Boletin Oficial de la Comunidad de Madrid',    'Madrid',               'https://www.bocm.es',                  'XML de sumario diario',           2),
 ('DOGC',  'Diari Oficial de la Generalitat de Catalunya', 'Cataluna',             'https://portaldogc.gencat.cat',        'API REST JSON (eadop-rest)',      3),
 ('BOJA',  'Boletin Oficial de la Junta de Andalucia',     'Andalucia',            'https://www.juntadeandalucia.es/boja', 'Feed Atom de boletin completo',   4),
 ('BORM',  'Boletin Oficial de la Region de Murcia',       'Murcia',               'https://www.borm.es',                  'API REST XML (services/boletin)', 5),
 ('DOCM',  'Diario Oficial de Castilla-La Mancha',         'Castilla-La Mancha',   'https://docm.castillalamancha.es',     'HTML de sumario diario',          6),
 ('BOCYL', 'Boletin Oficial de Castilla y Leon',           'Castilla y Leon',      'https://bocyl.jcyl.es',                'HTML de sumario diario',          7);

INSERT OR IGNORE INTO palabras_clave (termino, refuerzo) VALUES
 ('ayudas', 0), ('subvenciones', 0), ('convocatoria', 0), ('orden', 0),
 ('bases reguladoras', 0), ('incentivos', 0), ('financiacion', 0),
 ('financiacion publica', 0), ('programa de ayudas', 0), ('programa de subvenciones', 0),
 ('concurrencia competitiva', 0), ('concesion directa', 0), ('modernizacion', 0),
 ('inversion', 0), ('innovacion', 0), ('digitalizacion', 0), ('sostenibilidad', 0),
 ('eficiencia energetica', 0), ('industria', 0), ('pyme', 0), ('empresa', 0),
 ('empleo', 0), ('contratacion', 0), ('formacion', 0), ('internacionalizacion', 0);

INSERT OR IGNORE INTO palabras_clave (termino, refuerzo) VALUES
 ('pymes', 1), ('empresa industrial', 1), ('autonomo', 1), ('inversion productiva', 1);

INSERT OR IGNORE INTO destinatarios (correo, nombre) VALUES
 ('antonio@mova.es', 'Antonio'),
 ('j.javier@mova.es', 'J. Javier');

INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES
 ('hora_ejecucion',        '07:45',   'Hora de la ejecucion automatica diaria (HH:MM)'),
 ('dias_ejecucion',        'mon-fri', 'Dias de disparo en formato APScheduler'),
 ('zona_horaria',          'Europe/Madrid', 'Zona horaria del planificador'),
 ('planificador_activo',   '1',       'Activa o desactiva el disparo automatico'),
 ('modelo_extraccion',     'claude-sonnet-5', 'Modelo de la fase 3 (extraccion estructurada)'),
 ('modelo_relevancia',     'claude-haiku-4-5-20251001', 'Modelo de la fase 4 (relevancia)'),
 ('max_tokens_extraccion', '2000',    'Limite de tokens de la fase 3'),
 ('max_tokens_relevancia', '600',     'Limite de tokens de la fase 4'),
 ('hilos_modelo',          '3',       'Llamadas simultaneas al modelo'),
 ('umbral_difuso',         '92',      'Umbral de similitud de titulo para considerar duplicado'),
 ('dias_dedup',            '30',      'Dias hacia atras para la comparacion difusa'),
 ('dias_token_descarte',   '90',      'Caducidad de los enlaces de descarte del correo'),
 ('reintentos_boletin',    '3',       'Reintentos por boletin ante fallo de red'),
 ('copias_max',            '10',      'Numero de copias de seguridad que se conservan'),
 ('max_candidatas_ejecucion', '150',   'Tope de publicaciones que se mandan al modelo por ejecucion (0 = sin tope)'),
 ('smtp_servidor',         '',        'Servidor SMTP'),
 ('smtp_puerto',           '587',     'Puerto SMTP'),
 ('smtp_seguridad',        'starttls','starttls | ssl | ninguna'),
 ('smtp_usuario',          '',        'Usuario SMTP'),
 ('smtp_remitente',        '',        'Direccion remitente del correo diario'),
 ('smtp_nombre_remitente', 'MOVA Boletines Oficiales', 'Nombre visible del remitente'),
 ('url_publica',           '',        'URL base de los enlaces de descarte (vacio = la del entorno)'),
 ('terminos_refuerzo',     'pyme,pymes,empresa,empresas,empresa industrial,industria,autonomo,autonomos,inversion productiva,modernizacion industrial', 'Terminos que refuerzan la marca de alta relevancia'),
 ('primer_arranque',       '1',       'Marca de instalacion recien creada'),
 ('tarde_activa',          '1',       'Comprobacion de la tarde para boletines extraordinarios'),
 ('hora_tarde',            '20:00',   'Hora de la comprobacion de la tarde (HH:MM)'),
 ('alerta_activa',         '1',       'Correo urgente aparte para convocatorias de alta relevancia con plazo corto'),
 ('dias_alerta',           '15',      'Dias que faltan para el fin de plazo por debajo de los cuales se alerta'),
 ('semanal_activo',        '1',       'Resumen semanal por correo'),
 ('dia_semanal',           'mon',     'Dia del resumen semanal (mon..sun)'),
 ('hora_semanal',          '08:30',   'Hora del resumen semanal (HH:MM)'),
 ('dias_vencimiento_semanal', '30',   'El resumen semanal lista los plazos que vencen en estos dias'),
 ('esfuerzo_modelo',       'low',     'Esfuerzo de razonamiento en Sonnet 5 / Opus 5 / Opus 4.8 (low, medium, high)'),
 ('tope_mensual_usd',      '30',      'Tope de gasto mensual en la API en dolares (0 = sin tope)'),
 ('cambio_usd_eur',        '0.86',    'Tipo de cambio para mostrar el gasto en euros (editable)');

INSERT OR IGNORE INTO ajustes (clave, valor, cifrado, descripcion) VALUES
 ('anthropic_api_key', '', 1, 'Clave de API de Anthropic (cifrada con Fernet)'),
 ('smtp_clave',        '', 1, 'Contrasena SMTP (cifrada con Fernet)');
