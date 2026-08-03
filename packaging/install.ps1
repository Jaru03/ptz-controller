<#
.SYNOPSIS
    Instala ptz-controller para el usuario actual (sin permisos de administrador).

.DESCRIPTION
    Copia dist\ptz-controller.exe a %LOCALAPPDATA%\Programs\ptz-controller
    y crea accesos directos en el menú Inicio y en el escritorio. La
    configuración y los logs los crea el propio programa en
    %APPDATA%\ptz-controller la primera vez que arranca.

.PARAMETER Uninstall
    Desinstala la aplicación (conserva la configuración del usuario).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\install.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\install.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$AppId = 'ptz-controller'
$AppName = 'Controlador PTZ ONVIF'

$ProjectRoot = Split-Path -Parent $PSScriptRoot

# El .exe está junto al script cuando se descarga el paquete de la
# release, y en dist\ cuando se acaba de construir desde el código.
$SourceBinary = @(
    (Join-Path $PSScriptRoot 'ptz-controller.exe'),
    (Join-Path $ProjectRoot 'dist\ptz-controller.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$AppId"
$TargetBinary = Join-Path $InstallDir 'ptz-controller.exe'
$ConfigDir = Join-Path $env:APPDATA $AppId

$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$StartMenuLink = Join-Path $StartMenuDir "$AppName.lnk"
$DesktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk"

function New-Shortcut {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Target,
        [string]$Arguments = '--real'
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = Split-Path -Parent $Target
    $shortcut.IconLocation = $Target
    $shortcut.Description = 'Controla cámaras PTZ ONVIF con teclado o mando'
    $shortcut.Save()
}

if ($Uninstall) {
    Write-Host "Desinstalando $AppName…"
    foreach ($link in @($StartMenuLink, $DesktopLink)) {
        if (Test-Path $link) { Remove-Item $link -Force }
    }
    if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
    Write-Host '  Eliminado el ejecutable y los accesos directos.'
    if (Test-Path $ConfigDir) {
        Write-Host "  Se conserva la configuración en $ConfigDir"
        Write-Host "  Bórrela a mano si no la quiere."
    }
    return
}

if (-not $SourceBinary) {
    Write-Error @"
No se encuentra ptz-controller.exe.
Se ha buscado en $PSScriptRoot y en $ProjectRoot\dist
Si trabaja desde el código, constrúyalo antes con:
    uv run --group build python packaging\build.py
"@
}

Write-Host "Instalando $AppName para $env:USERNAME…"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item $SourceBinary $TargetBinary -Force
Write-Host "  Ejecutable: $TargetBinary"

New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
New-Shortcut -Path $StartMenuLink -Target $TargetBinary
Write-Host "  Menú Inicio: $StartMenuLink"

New-Shortcut -Path $DesktopLink -Target $TargetBinary
Write-Host "  Escritorio: $DesktopLink"

Write-Host ''
Write-Host "Listo. Búsquelo como '$AppName' en el menú Inicio."
Write-Host "  La configuración se creará en $ConfigDir\config.yaml"
Write-Host '  Edite ahí la IP, el usuario y la contraseña de su cámara.'
