@echo off
REM ============================================================================
REM  MOVA Boletines Oficiales - construir el ejecutable de Windows
REM
REM  IMPORTANTE: ejecutalo desde una ruta CORTA y sin sincronizar (por ejemplo
REM  C:\build\mova_boletines). PyInstaller falla con rutas largas y OneDrive
REM  puede bloquear ficheros a medio escribir.
REM ============================================================================
setlocal

echo.
echo [1/5] Comprobando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo    ERROR: no se encuentra Python en el PATH. Instala Python 3.11 o superior.
    exit /b 1
)

echo [2/5] Creando el entorno virtual (.venv)...
if not exist ".venv" (
    python -m venv .venv
    if errorlevel 1 (
        echo    ERROR: no se pudo crear el entorno virtual.
        exit /b 1
    )
)

echo [3/5] Instalando dependencias...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo    ERROR: fallo la instalacion de dependencias.
    exit /b 1
)
call .venv\Scripts\python.exe -m pip install pyinstaller==6.16.0

echo [4/5] Pasando las comprobaciones antes de empaquetar...
call .venv\Scripts\python.exe pruebas\test_esquema.py
if errorlevel 1 (
    echo    ERROR: la prueba del esquema no pasa. No se empaqueta.
    exit /b 1
)
call .venv\Scripts\python.exe pruebas\test_pipeline.py
if errorlevel 1 (
    echo    ERROR: la prueba del pipeline no pasa. No se empaqueta.
    exit /b 1
)

echo [5/5] Empaquetando con PyInstaller...
call .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean mova_boletines.spec
if errorlevel 1 (
    echo    ERROR: fallo el empaquetado.
    exit /b 1
)

echo.
echo ============================================================
echo  LISTO: dist\MOVA Boletines Oficiales.exe
echo.
echo  Para instalarlo: copia ese .exe a su carpeta definitiva y
echo  haz doble clic. Creara DATOS\ a su lado con la base de
echo  datos, la clave de cifrado, los registros y las copias.
echo.
echo  Para actualizar: sustituye SOLO el .exe. No toques DATOS\.
echo ============================================================
echo.
endlocal
