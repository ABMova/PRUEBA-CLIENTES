@echo off
rem Empaqueta MOVA DGX Spark Trainer con PyInstaller (carpeta dist\MOVA_DGX_Spark_Trainer).
rem Uso: empaquetar.bat            (usa el python del PATH)
rem      set PYTHON=C:\ruta\python.exe ^& empaquetar.bat
rem Si falla por rutas largas (MAX_PATH), copie el proyecto a una ruta corta (p. ej. C:\mdt) y empaquete alli.
setlocal
cd /d "%~dp0"
if not defined PYTHON set "PYTHON=python"

echo [1/4] Limpiando build\ y dist\
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/4] Comprobando PyInstaller
"%PYTHON%" -m PyInstaller --version >/dev/null 2>&1
if errorlevel 1 (
    echo PyInstaller no esta instalado. Ejecute: "%PYTHON%" -m pip install -r requirements-empaquetado.txt
    exit /b 1
)

echo [3/4] Regenerando el QSS desde la paleta
"%PYTHON%" -m ui.estilos.paleta
if errorlevel 1 goto error

echo [4/4] Generando el ejecutable
"%PYTHON%" -m PyInstaller --noconfirm --clean --log-level WARN mova_dgx_trainer.spec
if errorlevel 1 goto error
if not exist "dist\MOVA_DGX_Spark_Trainer\MOVA_DGX_Spark_Trainer.exe" goto error

echo.
echo OK: dist\MOVA_DGX_Spark_Trainer\MOVA_DGX_Spark_Trainer.exe
endlocal
exit /b 0

:error
echo.
echo ERROR: el empaquetado ha fallado. Revise los mensajes anteriores.
endlocal
exit /b 1
