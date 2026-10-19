# MOVA DGX Spark Trainer

Herramienta de escritorio para un solo usuario que entrena modelos de IA en local sobre una
NVIDIA DGX Spark (en el propio equipo o por SSH en la red local), sin navegador ni servidor web.
Cubre el ciclo completo:

1. **Proyecto**: nombre y tipo de tarea (`clasificacion_tabular`, `regresion_tabular`,
   `clasificacion_texto`; `ajuste_fino_llm` aparece deshabilitado como `[PENDIENTE]`).
2. **Importación**: Excel, CSV, TXT y JSON/JSONL, muchos a la vez o carpetas enteras, en un hilo,
   con progreso por fichero y resumen (importados / con avisos / descartados).
3. **Dataset**: objetivo, limpieza, imputación, codificación, escalado y división 70/15/15
   (semilla 42, estratificada en clasificación). Calcula y guarda la **línea base** (Dummy).
4. **Entrenamiento**: lanza `scripts_entrenamiento/entrenar_*.py` en local o en la Spark, con
   registro en vivo, cancelación y **reintentos** automáticos.
5. **Resultados**: KPIs, veredicto frente a umbrales y línea base, gráficas.
6. **Informe**: Word y PDF con el mismo contenido y anexo de trazabilidad.

Todo el historial queda en local (SQLite en `almacen/bd/trainer.db`). Funciona sin conexión:
sin fuentes remotas ni CDN.

## Instalación (código fuente)

Requisitos: Windows 10/11 y Python 3.12 o superior (probado con 3.14.6).

```bat
python -m venv %LOCALAPPDATA%\MOVA\venvs\dgx_trainer
%LOCALAPPDATA%\MOVA\venvs\dgx_trainer\Scripts\activate
pip install -r requirements.txt
```

El entorno virtual se crea fuera de OneDrive a propósito: miles de ficheros sincronizándose y las
rutas largas dan problemas.

## Ejecución

```bat
python main.py
```

Comprobaciones:

```bat
pytest pruebas -q                       :: 33 pruebas, incluye humo de punta a punta e interfaz
python pruebas\humo_end2end.py          :: humo con salida legible
set QT_QPA_PLATFORM=offscreen && python main.py --prueba-arranque
```

## Ejecutable

```bat
pip install -r requirements-empaquetado.txt
empaquetar.bat
```

Genera `dist\MOVA_DGX_Spark_Trainer\MOVA_DGX_Spark_Trainer.exe` (ventana sin consola, con icono).
Se reparte la carpeta entera. Si PyInstaller falla por rutas largas (MAX_PATH), copie el proyecto a
una ruta corta (p. ej. `C:\mdt`) y empaquete allí.

**Importante**: el ejecutable no incluye un intérprete para los scripts de entrenamiento. En modo
local hace falta un Python con scikit-learn en el PATH o indicado en Configuración → Intérprete
local. En modo remoto se usa el Python de la Spark.

## Actualización

- **Código fuente**: actualizar los ficheros, `pip install -r requirements.txt` y arrancar. Las
  migraciones de la base de datos se aplican solas al arrancar (versión en `PRAGMA user_version`)
  y antes se hace una copia de seguridad.
- **Ejecutable**: sustituir la carpeta del programa **conservando `almacen\`**, que está junto al
  `.exe`. Nunca borre `almacen\` al actualizar.

## El almacén (datos del usuario)

> OJO: `datos/` es **código** (esquema, repositorio, migraciones, copias) y se versiona.
> Los datos del usuario van en `almacen/`.

`almacen/` se crea junto al ejecutable (o junto a `main.py`). Si ahí no se puede escribir, se usa
`%LOCALAPPDATA%\MOVA\DGXSparkTrainer\almacen\` y se anota en `almacen/logs/aplicacion.log`. La
ubicación no es configurable.

| Carpeta | Contenido |
|---|---|
| `bd/trainer.db` | SQLite: proyectos, datasets, ficheros_origen, configuraciones, ejecuciones, metricas, logs, informes |
| `backups/` | copias automáticas (10 últimas) |
| `datasets/p<id>/` | dataset bruto combinado y particiones train/val/test |
| `modelos/p<id>_<nombre>/e<ejecución>/` | config.json, script, resultado.json, modelo, predicciones, log |
| `logs/` | log de la aplicación y log íntegro de cada ejecución |
| `informes/` | Word, PDF y gráficas |
| `config/` | conexión SSH cifrada (`conexion.enc`), sal y `known_hosts` |

## Copias de seguridad

Al arrancar se copia la base de datos en `almacen/backups/` (API de copia de SQLite) y se
conservan las 10 últimas. En Configuración hay botones para crear una copia y para restaurar la
seleccionada; antes de restaurar se guarda una copia del estado actual. Las copias cubren la base
de datos; los ficheros de `modelos/`, `datasets/` e `informes/` conviene incluirlos en la copia
general del equipo.

## Modos de ejecución

- **Local**: `subprocess` sobre el intérprete indicado.
- **Remoto por SSH** (paramiko): usuario, host, puerto y clave privada o contraseña. Se suben
  configuración, dataset y script por SFTP a `~/mova_dgx_trainer/trabajos/<proyecto>_<ejecución>`
  y al terminar se bajan los artefactos. Para la Spark de MOVA: host `192.168.1.240` en la oficina
  o `100.85.10.107` por Tailscale, usuario `mova_ia`. El Python de sistema de la Spark necesita
  scikit-learn para `entrenar_sklearn.py` [PENDIENTE: comprobar con «Comprobar entorno»].
- La primera conexión acepta y guarda la huella del host (`almacen/config/known_hosts`); si
  después cambia, se rechaza.
- «Comprobar entorno» ejecuta `nvidia-smi`, `python -V` e importa sklearn/torch/tensorflow; lo no
  detectado se marca `[PENDIENTE]`.

## Contrato de los scripts de entrenamiento

`python <script> --config config.json --salida resultado.json`. Por stdout, una línea JSON por
evento (`{"evento":"progreso","epoca":3,"total":20,"perdida":0.41,"metrica":0.78}` o
`{"evento":"log","texto":"..."}`); lo que no se pueda leer se muestra como log. El resultado lleva
`estado` (ok|error), `metricas`, `ruta_modelo`, `duracion_s`, `hiperparametros`, `versiones` y
`error`; el código de salida es 0 solo si `estado == ok`.

## Evaluación y reintentos

- Umbrales por defecto (editables): clasificación `métrica objetivo ≥ 0.70` y `≥ baseline + 0.10`;
  regresión `r2 ≥ 0.50` y `mae ≤ 0.90 × baseline.mae`.
- Reintentos: máximo 3 (0 los desactiva). Error de memoria CUDA → `batch_size` a la mitad; otro
  fallo técnico → un reintento con la misma configuración; desempeño insuficiente → siguiente
  combinación de `nucleo/rejillas.py`. Cada reintento es una ejecución nueva.

## Decisiones abiertas [PENDIENTE]

No están cerradas; la aplicación las muestra en ámbar.

1. **Frameworks**: scikit-learn está verificado. PyTorch (`entrenar_torch.py`) y TensorFlow
   (`entrenar_tensorflow.py`) existen pero **no están verificados** (no hay torch ni tensorflow
   en el equipo de desarrollo; los contenedores de la Spark no salen a internet).
2. **Métricas prioritarias**: la métrica objetivo es configurable (f1_macro por defecto en
   clasificación; r2 + mae en regresión).
3. **Ajuste genérico o específico** por proyecto.
4. **Requisitos de versionado** de modelos y datasets (hoy: hash SHA-256 de ficheros y datasets,
   carpetas por ejecución, nada se sobrescribe).
5. **SQLite**: es una propuesta, no una petición.
6. **Alcance del ajuste fino de LLM** (`ajuste_fino_llm`, deshabilitado).

## Riesgos

- **Modo local empaquetado**: depende de un Python externo con scikit-learn.
- **SSH con TOFU**: la primera conexión confía en la huella del host. Verifíquela si la red no es
  de confianza.
- **Clave derivada de la máquina**: `conexion.enc` no se puede abrir en otro equipo; al cambiar de
  equipo hay que volver a introducir la conexión.
- **Ficheros muy grandes**: por encima de 1 GB se importa una muestra; el resto del fichero no
  entra en el entrenamiento.
- **Cancelación remota**: se cierra el canal SSH (el proceso recibe SIGHUP). Un script que ignore
  esa señal seguiría en la Spark.
- **PyTorch/TensorFlow** sin verificar (ver decisiones abiertas).
- **Copias**: solo de la base de datos, no de los artefactos.

## Mejoras futuras

- **Ajuste fino de LLM**: en la Spark ya existe un flujo LoRA con NeMo AutoModel en
  `/opt/entrenamiento` (`entrenar.sh`, `publicar.sh`, `GUIA.md`), probado de punta a punta con
  Qwen3.5-9B hasta Ollama. Encaja con `ajuste_fino_llm` cuando se confirme su alcance: un script
  que siga el contrato `--config/--salida` y llame a ese flujo.
- Verificar PyTorch y TensorFlow en la Spark e incluir un entorno con GPU.
- Importar el modelo entrenado para predecir sobre ficheros nuevos.
- Copia completa del almacén (no solo la base de datos).
- Comparativa entre proyectos y búsqueda de hiperparámetros más amplia.

## Estructura

```
main.py                      arranque, QSS, cierre ordenado, --prueba-arranque
ui/                          ventana, pasos, configuración, widgets/, estilos/, recursos/
nucleo/                      coordinador (servicios), importador, preparador, entrenador,
                             evaluador, reintentos, rejillas, exportador, graficas, contexto
datos/                       CÓDIGO: esquema, repositorio (único SQL), migraciones, backup
infra/                       ejecutor_ssh (local/SSH), cifrado (Fernet), rutas, hilos, registro
scripts_entrenamiento/       entrenar_sklearn.py, entrenar_torch.py, entrenar_tensorflow.py
pruebas/                     pytest, humo_end2end.py, recursos/ generados
```
