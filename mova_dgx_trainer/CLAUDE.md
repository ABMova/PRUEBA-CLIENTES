# MOVA DGX Spark Trainer · contexto para Claude Code

Aplicación de escritorio (PySide6) para un solo usuario que entrena modelos en local o en la
NVIDIA DGX Spark por SSH: proyecto → importación → dataset → entrenamiento → resultados → informe.
Responder y documentar en español.

## Comandos

```bash
python main.py                                  # arrancar
QT_QPA_PLATFORM=offscreen python main.py --prueba-arranque   # arranque automático (código 0 = bien)
pytest pruebas -q                               # pruebas (incluye la de humo y la de interfaz)
python pruebas/humo_end2end.py                  # humo de punta a punta con salida legible
python -m ui.estilos.paleta                     # regenerar ui/estilos/mova.qss tras tocar la paleta
python -m ui.recursos.generar_recursos          # regenerar icono.ico e imagenes_base64.py
empaquetar.bat                                  # ejecutable en dist\MOVA_DGX_Spark_Trainer\
```

## ADVERTENCIA: `datos/` frente a `almacen/`

- `datos/` es **código** (esquema, repositorio, migraciones, copias). Se versiona y se empaqueta.
  Nunca lo añada a .gitignore.
- `almacen/` son los **datos del usuario** (bd, backups, modelos, logs, informes, datasets, config
  cifrada). Va junto al ejecutable; si ahí no se puede escribir, en
  `%LOCALAPPDATA%\MOVA\DGXSparkTrainer\almacen\` (se anota en el log). No es configurable.
  Nunca se versiona ni se empaqueta.

## Reglas de arquitectura

- Capas: `ui/` → `nucleo/coordinador.py` (servicios) → `datos/repositorio.py` (único sitio con SQL).
  Los widgets no tocan la base de datos ni reglas de dominio.
- `nucleo/` no importa Qt: recibe un `Contexto` (progreso, log, evento, cancelado).
- Todo trabajo largo va en `infra/hilos.TrabajoFuncion` (QThread con cancelación cooperativa).
- Errores al usuario: dos frases, qué ha pasado y qué hacer (`ErrorServicio(que_paso, que_hacer)`).
- Nada se inventa: lo ausente se muestra como `[PENDIENTE: dato]` en ámbar.
- Un solo botón dorado (`tipo="principal"`) por pantalla. Colores solo desde `ui/estilos/paleta.py`.
- Cada reintento es una fila nueva en `ejecuciones`; nunca se sobrescribe la anterior.
- Esquema: añadir migraciones al final de `datos/esquema.MIGRACIONES` (idempotentes); no editar las
  ya publicadas.
- Los scripts de `scripts_entrenamiento/` son autocontenidos (se copian tal cual a la Spark) y
  cumplen el contrato `--config/--salida` con eventos JSONL por stdout.

## Trampas conocidas

- Al salir, Qt puede dar «access violation» si Python destruye la QApplication antes que los
  widgets: `main.py` hace un cierre ordenado (`app.shutdown()`); no quitarlo.
- La plataforma offscreen no ve las fuentes de Windows: `main.py` fija `QT_QPA_FONTDIR`.
- El .xlsx de `pruebas/recursos/` guarda fecha de creación: `generar()` solo escribe lo que falte.
- Empaquetado: si PyInstaller falla por rutas largas (OneDrive), copiar a una ruta corta.
- Empaquetado, el modo local necesita un Python con scikit-learn en el PATH (o indicado en
  Configuración): el ejecutable no lleva intérprete para los scripts.
