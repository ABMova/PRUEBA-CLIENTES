@echo off
REM ============================================================================
REM  MOVA Boletines Oficiales - quitar la tarea programada de Windows
REM
REM  Quita la tarea que arranca la herramienta sola. NO borra ningun dato:
REM  la base de datos, el historico y las copias se quedan como estan.
REM  Despues de esto, la vigilancia diaria solo ocurrira si abres la
REM  herramienta a mano antes de la hora configurada.
REM ============================================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0despliegue\tarea_windows.ps1" -Quitar
echo.
pause
