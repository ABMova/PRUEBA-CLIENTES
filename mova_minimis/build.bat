@echo off
rem MOVA Minimis - compila el ejecutable de Windows.
rem Se compila desde una ruta corta fuera de OneDrive (C:\build\mova_minimis): las rutas
rem largas y la sincronizacion rompen PyInstaller. El resultado queda en
rem C:\build\mova_minimis\dist\MOVA Minimis.exe y se copia a .\dist del proyecto.
setlocal
set ORIGEN=%~dp0
set DESTINO=C:\build\mova_minimis
set VENV=C:\build\venvs\mova_minimis

echo == Copiando el codigo a %DESTINO%
if not exist "%DESTINO%" mkdir "%DESTINO%"
robocopy "%ORIGEN%." "%DESTINO%" /MIR /XD data data-dev build dist __pycache__ .git tests /XF .env *.db cipher.key /NFL /NDL /NJH /NJS >nul
if %ERRORLEVEL% GEQ 8 (echo Fallo al copiar & exit /b 1)

if not exist "%VENV%\Scripts\python.exe" (
  echo == Creando entorno virtual en %VENV%
  python -m venv "%VENV%" || exit /b 1
)
echo == Instalando dependencias
"%VENV%\Scripts\python.exe" -m pip install -q --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -q -r "%DESTINO%\requirements.txt" || exit /b 1

echo == Compilando
pushd "%DESTINO%"
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean mova_minimis.spec || (popd & exit /b 1)
popd

if not exist "%ORIGEN%dist" mkdir "%ORIGEN%dist"
copy /Y "%DESTINO%\dist\MOVA Minimis.exe" "%ORIGEN%dist\MOVA Minimis.exe" >nul
echo == Listo: %ORIGEN%dist\MOVA Minimis.exe
endlocal
