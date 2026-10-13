# MOVA Minimis

Consulta el saldo disponible de ayudas de minimis de los clientes a partir de la
**Base de Datos Nacional de Subvenciones (BDNS)** y genera informes en Word, PDF y Excel.

- Lee los CIF de documentos (PDF, imágenes, Excel, Word, CSV, TXT) o de la entrada manual,
  validando el dígito de control.
- Consulta en la BDNS **real** (API pública de infosubvenciones.es, sin clave) todas las
  concesiones de minimis de cada CIF, con su reglamento, fecha, importe y convocatoria.
- Calcula el saldo con la normativa vigente y explica cuándo sale cada ayuda del periodo.
- Deja rastro de todo: usuario, IP, parámetros, documentos (con su huella SHA-256) e informes.

## Normativa aplicada

| Reglamento | Techo | Periodo |
|---|---|---|
| (UE) 2023/2831, general (desde 01/01/2024) | 300.000 € por única empresa | cualquier periodo de 3 años (móvil) |
| (UE) 1407/2013, general (hasta 31/12/2023) | 200.000 € | 3 ejercicios fiscales |
| (UE) 1408/2013, agrícola | sublímite 50.000 € desde el 16/12/2024 (Reg. 2024/3118); 25.000 € desde el 02/12/2024 (RD 1139/2024); 20.000 € antes. Suma al techo general | 3 años |
| (UE) 717/2014, pesca | sublímite 40.000 € en España desde el 02/12/2024 (Reg. 2023/2391 y RD 1139/2024); 30.000 € antes. Suma al techo general | 3 ejercicios (se aproxima con el periodo general) |
| (UE) 2023/2832, SIEG | 750.000 € combinado con las generales | 3 años |

Estados: **Saldo disponible** (más de 5.000 €), **En el límite** (entre 0 y 5.000 €),
**Límite superado** (saldo negativo) y **Pendiente** (la BDNS no respondió).

> El encargo original hablaba de 200.000 € y del Reglamento 1407/2013. Esa norma dejó de
> aplicarse el 31/12/2023; la aplicación usa el 2023/2831 y conserva el cálculo por
> ejercicios para revisar periodos anteriores.

Lo que la aplicación **no** puede saber y por eso marca como `[PENDIENTE: ...]`:
- las ayudas de las empresas vinculadas (el techo es por *única empresa*, art. 2.2);
- las concesiones que aún no están registradas en la BDNS (las ventajas fiscales llegan con
  meses de retraso). Para ambas, el informe permite añadir **ayudas declaradas por el
  cliente**, que se suman al cálculo y quedan identificadas como tales.

## Instalación

### Ejecutable (recomendado)
1. Copie `MOVA Minimis.exe` donde quiera y ábralo. Se abre el navegador en
   http://127.0.0.1:5000.
2. Entre con `admin@local` / `TemporalAdmin123`; la aplicación obliga a cambiar la contraseña.
3. En 🔒 Configuración: añada la clave de la API de Anthropic si quiere que Claude lea los
   documentos escaneados (opcional) y cree los usuarios del equipo.
4. Para cerrarla: 🔒 Configuración → *Cerrar la aplicación* (el .exe no tiene ventana).

Los datos se guardan en `%LOCALAPPDATA%\MOVA Minimis\data` (fuera de OneDrive a propósito:
SQLite se corrompe en carpetas sincronizadas). Para cambiarla, cree un `.env` junto al .exe
con `MOVA_MINIMIS_DATOS=C:\ruta`.

### Desde el código
```
python -m venv C:\build\venvs\mova_minimis
C:\build\venvs\mova_minimis\Scripts\pip install -r requirements.txt
C:\build\venvs\mova_minimis\Scripts\python app.py
```
Desde el código los datos van a `%LOCALAPPDATA%\MOVA Minimis\data-dev`.

### OCR (opcional)
Tesseract se instala aparte: https://github.com/UB-Mannheim/tesseract/wiki (marque el
idioma español). Sin Tesseract ni clave de Claude, los PDF escaneados y las imágenes no se
pueden leer y la aplicación lo avisa para introducir esos datos a mano.

## Uso
1. **Búsqueda**: arrastre documentos o escriba `CIF ; razón social` (una línea por cliente).
   Revise la lista: los identificadores con dígito de control incorrecto o ilegibles por OCR
   se muestran aparte y no se consultan.
2. Elija el periodo: **tres años móviles** hasta la fecha prevista de concesión (vigente) o
   **ejercicios** concretos.
3. **Resultados**: progreso en vivo, saldo por cliente, detalle de cada concesión con enlace
   a la BDNS, calendario de salida de ayudas y pendientes.
4. **Exportar**: Word, PDF, Excel (resumen, detalle y referencias) o JSON.

El **Historial** busca consultas anteriores por razón social o CIF.

## Roles
| Rol | Puede |
|---|---|
| Administrador | todo, más usuarios, auditoría, copias y configuración |
| Consultor | crear consultas, subir documentos, añadir ayudas declaradas y exportar |
| Solo lectura | ver consultas anteriores |

Un usuario desactivado queda fuera en su siguiente clic.

## Copia de seguridad
- **Automática** en cada arranque (`data\backups`, se conservan las 10 últimas).
- **Manual**: Configuración → Copias de seguridad → *Descargar copia (.zip)* (base de datos y
  documentos cifrados).
- **Restaurar**: subir un `.zip` o `.db`; se comprueba la integridad y antes se guarda una
  copia del estado actual.
- La llave `data\cipher.key` **no** va en el .zip. Guárdela aparte: sin ella no se pueden leer
  los documentos subidos ni la clave de Claude en otro equipo.

## Actualizar
Cierre la aplicación y sustituya el .exe. El esquema de la base se aplica solo al arrancar
(las columnas nuevas se añaden sin tocar los datos). La copia automática del arranque queda
como respaldo.

## Estructura
```
app.py              arranque, sesión, CSRF, cabeceras de seguridad
config.py           rutas y parámetros (datos fuera del .exe)
routes/             HTTP y permisos; orquestador.py encadena los agentes en un hilo
logic/              los cinco agentes, sin SQL ni HTTP
  parser.py         1  · extracción y validación de CIF/NIF/NIE (texto, OCR, Claude)
  consultor.py      2a · consulta a la BDNS
  calculador.py     2b · saldo según la normativa (determinista)
  generador.py      3a · informe estructurado (determinista)
  exportador.py     3b · Word, PDF y Excel
models/             db.py (único módulo con SQL) y schema.sql idempotente
auth/               contraseñas PBKDF2, cifrado Fernet, roles
integrations/       web_scraper.py (API de la BDNS) y claude_api.py
templates/, static/ interfaz MOVA IA (tema oscuro y dorado, sin CDN)
tests/              pruebas sin red: python -m unittest discover -s tests
```

## Decisiones respecto al encargo
- **BDNS real, no simulada**: la API pública existe y se usa (`/terceros`, `/minimis/busqueda`,
  `/convocatorias`). No hay dataset de ejemplo con CIF reales y ayudas inventadas.
- **Claude solo donde aporta**: leer documentos que no tienen texto. El cálculo, el informe y
  la exportación son deterministas (mismas entradas, mismo resultado) y no gastan API.
- **Modelos** actuales: Claude Opus 5.5 (por defecto), Sonnet 5.5 y Haiku 5.5.
- Los iconos van incrustados en base64 al servir la página (no hay `icons.js`).

## Riesgos conocidos
- La BDNS es dinámica: una concesión puede registrarse o corregirse después de la consulta.
  La caché local guarda las respuestas 12 horas (*Vaciar caché* en Configuración).
- Reutilización de datos sujeta al aviso legal de infosubvenciones.es; los informes lo citan.
- El periodo «ejercicios» con años 2024 o posteriores es orientativo: la norma vigente es móvil.
