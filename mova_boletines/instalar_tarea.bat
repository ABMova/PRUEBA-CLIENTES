@echo off
REM ============================================================================
REM  MOVA Boletines Oficiales - registrar la tarea programada de Windows
REM
REM  Doble clic aqui despues de instalar la herramienta. Registra una tarea que
REM  la arranca al iniciar sesion y la vuelve a levantar cada dia laborable a
REM  las 07:30, quince minutos antes de la vigilancia, por si el equipo se
REM  encendio tarde. Si ya esta en marcha, no hace nada.
REM
REM  No hace falta ser administrador: la tarea es del usuario actual.
REM  Para quitarla: desinstalar_tarea.bat
REM ============================================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0despliegue\tarea_windows.ps1" %*
echo.
pause
