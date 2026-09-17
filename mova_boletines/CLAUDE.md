# MOVA Boletines Oficiales — comandos que no se adivinan

Todo se ejecuta desde `mova_boletines/`. El entorno virtual es `.venv` y está
creado con **Python 3.11** (no con el 3.14 del sistema: PyInstaller y algunas
ruedas no lo admiten todavía).

## Arrancar

```bash
.venv/Scripts/python.exe app.py
```

Sirve en `http://127.0.0.1:8770` con waitress, abre el navegador y programa la
vigilancia diaria. Variables útiles en la misma línea:

```bash
MOVA_PUERTO=8771 MOVA_ABRIR_NAVEGADOR=0 .venv/Scripts/python.exe app.py
```

**Nunca con varios workers.** El progreso de la ejecución vive en memoria: un
solo proceso con hilos.

## Comprobar

```bash
.venv/Scripts/python.exe pruebas/test_esquema.py            # esquema idempotente, cifrado, contrasenas
.venv/Scripts/python.exe pruebas/test_pipeline.py           # pipeline entero con boletin y modelo simulados
.venv/Scripts/python.exe pruebas/test_web.py                # arranca el servidor real y prueba sesiones y permisos
.venv/Scripts/python.exe pruebas/generar_correo_ejemplo.py  # escribe _DATOS/correo_ejemplo.html
.venv/Scripts/python.exe pruebas/test_boletines_vivo.py 2026-09-17   # boletines reales (necesita internet)
```

Las cuatro primeras no salen a internet ni gastan API. Cada una devuelve 0 si
pasa y 1 si falla, así que sirven tal cual en un gancho de integración.

## Tarea programada de Windows

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File despliegue/tarea_windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File despliegue/tarea_windows.ps1 -Quitar
```

O doble clic en `instalar_tarea.bat` / `desinstalar_tarea.bat`. La tarea solo
mantiene la herramienta encendida; la vigilancia la dispara el planificador
interno a la hora de Ajustes. El script detecta si hay `.exe` compilado y, si
no, usa `.venv\Scripts\pythonw.exe app.py`.

Arrancar como lo hace la tarea (sin ventana ni navegador):

```bash
.venv/Scripts/pythonw.exe app.py --sin-navegador
```

Un segundo arranque sobre el mismo puerto no hace nada y sale con codigo 0: lo
comprueba `ya_hay_instancia()` pidiendo `/salud` antes de tocar la base de datos.

## Empaquetar

```bash
construir.bat
```

Desde una ruta **corta y fuera de OneDrive** (`C:\build\mova_boletines`):
PyInstaller falla con rutas largas y OneDrive bloquea ficheros a medio
escribir. El resultado es `dist\MOVA Boletines Oficiales.exe`.

## Instalar dependencias

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Si hay que rehacer el entorno:

```bash
"$LOCALAPPDATA/../Roaming/uv/python/cpython-3.11.15-windows-x86_64-none/python.exe" -m venv .venv
```

## Dónde están los datos al desarrollar

En `_DATOS/`, no en `DATOS/`: Windows no distingue mayúsculas y `DATOS/`
chocaría con el paquete de código `datos/`. Para empezar de cero:

```bash
rm -rf _DATOS && .venv/Scripts/python.exe app.py
```

El usuario inicial es `admin` / `MovaBoletines2026`, con cambio obligatorio en
el primer acceso.

## Reglas del proyecto

- `datos/repositorio.py` es el **único** módulo que ejecuta SQL.
- `web/rutas.py` no contiene lógica de dominio; `negocio/` no sabe de HTTP.
- `integraciones/anthropic_cliente.py` es la **única** puerta a la API.
- Si un dato no está en la publicación se escribe `[PENDIENTE: dato]`. Nunca se
  rellena con un valor plausible.
- Los adaptadores de boletín llevan en su cabecera la URL usada, la fecha de
  comprobación y las instrucciones para repararlos.
