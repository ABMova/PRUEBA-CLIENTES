<#
    Registra (o quita) la tarea programada de Windows que mantiene viva
    MOVA Boletines Oficiales para que la vigilancia de las 07:45 se dispare.

    QUE HACE LA TAREA
      - Arranca la herramienta al iniciar sesion el usuario, minimizada y sin
        abrir el navegador.
      - Vuelve a intentarlo cada dia laborable unos minutos antes de la
        vigilancia de la manana (07:30) y de la comprobacion de la tarde
        (19:45), por si el equipo se encendio tarde o la herramienta se
        cerro. Si ya esta en marcha, el segundo arranque se detecta solo y no
        hace nada: la herramienta comprueba si su puerto ya responde.
      - Si el proceso se cae, Windows lo reintenta tres veces.

    POR QUE ASI
      La vigilancia la dispara el planificador interno de la herramienta, no
      Windows. La tarea solo se ocupa de que la herramienta ESTE ENCENDIDA a esa
      hora. Asi el historico, la cancelacion y el progreso en vivo siguen
      funcionando igual que si la arrancases a mano.

    USO
        powershell -ExecutionPolicy Bypass -File despliegue\tarea_windows.ps1
        powershell -ExecutionPolicy Bypass -File despliegue\tarea_windows.ps1 -Quitar
        powershell -ExecutionPolicy Bypass -File despliegue\tarea_windows.ps1 -Hora 07:30

    No necesita permisos de administrador: la tarea se crea para el usuario
    actual. Si el equipo esta apagado a la hora fijada, la vigilancia se hara
    en cuanto se encienda e inicie sesion (ese dia, en el momento del arranque).
#>

[CmdletBinding()]
param(
    [string]$Nombre = "MOVA Boletines Oficiales",
    [string]$Hora = "07:30",
    [string]$HoraTarde = "19:45",
    [ValidateSet("Diaria", "Laborables")]
    [string]$Dias = "Laborables",
    [int]$Puerto = 0,
    [string]$Programa = "",
    [switch]$Quitar
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot

function Escribir($texto, $color = "Gray") { Write-Host "  $texto" -ForegroundColor $color }

Write-Host ""
Write-Host "MOVA Boletines Oficiales - tarea programada de Windows" -ForegroundColor Yellow
Write-Host ""

# ----------------------------------------------------------------- quitar --
if ($Quitar) {
    if (Get-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false
        Escribir "Tarea '$Nombre' eliminada." "Green"
        Escribir "La herramienta ya no se arrancara sola: la vigilancia de las 07:45"
        Escribir "solo ocurrira si la abres tu."
    } else {
        Escribir "No existe ninguna tarea llamada '$Nombre'. No hay nada que quitar."
    }
    Write-Host ""
    exit 0
}

# ------------------------------------------------- que se ejecuta y con que --
# Orden de busqueda: lo que diga -Programa, el .exe instalado al lado, el .exe
# recien compilado en dist\, y por ultimo el codigo fuente con su entorno.
$exeInstalado = Join-Path $raiz "MOVA Boletines Oficiales.exe"
$exeCompilado = Join-Path $raiz "dist\MOVA Boletines Oficiales.exe"
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$appPy = Join-Path $raiz "app.py"

$argumentos = @("--sin-navegador")
if ($Puerto -gt 0) { $argumentos += @("--puerto", "$Puerto") }

if ($Programa) {
    if (-not (Test-Path $Programa)) {
        Escribir "No existe el programa indicado: $Programa" "Red"
        exit 1
    }
    $programa = (Resolve-Path $Programa).Path
    $raiz = Split-Path -Parent $programa
    $modo = "ejecutable indicado a mano"
} elseif (Test-Path $exeInstalado) {
    $programa = $exeInstalado
    $modo = "ejecutable instalado"
} elseif (Test-Path $exeCompilado) {
    $programa = $exeCompilado
    $raiz = Split-Path -Parent $exeCompilado
    $modo = "ejecutable recien compilado (dist)"
} elseif ((Test-Path $pythonw) -and (Test-Path $appPy)) {
    $programa = $pythonw
    $argumentos = @("`"$appPy`"") + $argumentos
    $modo = "codigo fuente con el entorno virtual"
} else {
    Escribir "No encuentro el ejecutable ni .venv\Scripts\pythonw.exe" "Red"
    Escribir "Compila con construir.bat, o pasa la ruta con -Programa." "Red"
    exit 1
}

Escribir "Modo      : $modo"
Escribir "Programa  : $programa"
Escribir "Argumentos: $($argumentos -join ' ')"
Escribir "Carpeta   : $raiz"

# --------------------------------------------------------------- disparos --
$accion = New-ScheduledTaskAction -Execute $programa -Argument ($argumentos -join " ") -WorkingDirectory $raiz

$disparos = @(New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
foreach ($horaDisparo in @($Hora, $HoraTarde)) {
    if (-not $horaDisparo) { continue }
    if ($Dias -eq "Laborables") {
        $disparos += New-ScheduledTaskTrigger -Weekly -At $horaDisparo `
            -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday
    } else {
        $disparos += New-ScheduledTaskTrigger -Daily -At $horaDisparo
    }
}

$ajustes = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew `
    -Hidden

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$descripcion = "Mantiene encendida la herramienta MOVA Boletines Oficiales para que su " +
               "vigilancia diaria de ayudas y subvenciones se dispare a la hora configurada " +
               "en Ajustes. Si ya esta en marcha, este arranque no hace nada."

if (Get-ScheduledTask -TaskName $Nombre -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false
    Escribir "Tarea anterior sustituida."
}

Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $disparos `
    -Settings $ajustes -Principal $principal -Description $descripcion | Out-Null

$tarea = Get-ScheduledTask -TaskName $Nombre
$info = Get-ScheduledTaskInfo -TaskName $Nombre

Write-Host ""
Escribir "Tarea '$Nombre' registrada." "Green"
Escribir "Estado          : $($tarea.State)"
Escribir "Disparos        : al iniciar sesion y $($Dias.ToLower()) a las $Hora y a las $HoraTarde"
Escribir "Proxima vez     : $($info.NextRunTime)"
Write-Host ""
Escribir "La vigilancia (07:45) y la comprobacion de la tarde (20:00) las dispara la"
Escribir "herramienta a la hora de Ajustes: esta tarea solo se asegura de que este encendida."
Write-Host ""
Escribir "Comprobar : Get-ScheduledTaskInfo -TaskName '$Nombre'"
Escribir "Probar    : Start-ScheduledTask -TaskName '$Nombre'"
Escribir "Quitar    : ...\tarea_windows.ps1 -Quitar"
Write-Host ""
