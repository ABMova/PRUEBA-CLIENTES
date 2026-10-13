# MOVA Minimis · notas para Claude Code

Flask + waitress + SQLite, empaquetado con PyInstaller (no Electron). Responder siempre en español.

## Comandos
- Entorno: `C:\build\venvs\mova_minimis` (fuera de OneDrive). Reinstalar:
  `C:\build\venvs\mova_minimis\Scripts\pip install -r requirements.txt`
- Arrancar: preview «MOVA Minimis» de `.claude/launch.json` (puerto 5000), o
  `C:\build\venvs\mova_minimis\Scripts\python app.py`. waitress no recarga: reiniciar tras cambiar Python.
- Pruebas (sin red): `C:\build\venvs\mova_minimis\Scripts\python -m unittest discover -s tests -v`
- Compilar el .exe: ejecutar `build.bat` desde PowerShell (`cmd /c "<ruta>\build.bat"`): la ruta
  del proyecto lleva una coma («MOVA STRATEGY,SL») y `cmd //c` desde Git Bash no lo encuentra.
  Copia el código a `C:\build\mova_minimis`, compila allí y deja `dist\MOVA Minimis.exe`.
- Entregar: copiar el .exe a `OneDrive\00_IA-AFBM\CLAUDE\EJECUTABLES` como `MOVAMinimis-X.Y.Z.exe`
  y comprobar el hash.

## Datos
- Desarrollo: `%LOCALAPPDATA%\MOVA Minimis\data-dev`; ejecutable: `...\data`. Nunca en OneDrive.
- `cipher.key` cifra la clave de Claude y los documentos subidos.
- Para probar el .exe sin tocar datos reales: `MOVA_MINIMIS_DATOS=<temporal>` y `MOVA_PUERTO=5055`
  (si el puerto está ocupado el .exe solo abre el navegador y sale).

## Reglas del dominio
- Techo general 300.000 € en 3 años móviles (Reg. 2023/2831); 200.000 € por ejercicios antes de 2024.
- Agrícola y pesca suman al techo general; SIEG combinado hasta 750.000 €.
- Nunca inventar datos: lo que falta se marca `[PENDIENTE: ...]`.
- La BDNS filtra en silencio si el parámetro no es exactamente el del portal (`beneficiario=<id>` sale
  de `/terceros?ambito=M&busqueda=<CIF>`); fechas en dd/mm/aaaa.

## Aspecto
Desde la 1.0.4 la aplicación viste como el CRM de MOVA (skill mova-crm-claro): `static/mova-crm.css` es copia literal
de la hoja de la skill y no se edita; lo propio va en `static/minimis.css`. Logotipo MOVA IA negro en el menú y en el
acceso. Los informes (Word, PDF, Excel) NO siguen este aspecto: el usuario pidió dejarlos como salían.

## Arquitectura
`logic/` no importa Flask ni `models`: la red, la caché y el progreso se inyectan desde
`routes/orquestador.py`. Todo el SQL vive en `models/db.py`. Columnas nuevas: añadir a
`COLUMNAS_POSTERIORES` además de a `schema.sql`.
