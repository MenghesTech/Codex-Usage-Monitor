$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    py -3 -m venv $venv
}

& $python -m pip install --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias de build." }

foreach ($name in @("build", "dist")) {
    $target = Join-Path $root $name
    if (Test-Path -LiteralPath $target) {
        $resolved = (Resolve-Path -LiteralPath $target).Path
        if ((Split-Path -Parent $resolved) -ne $root) {
            throw "Ruta de limpieza insegura: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

& $python tools\generate_icon.py
if ($LASTEXITCODE -ne 0) { throw "No se pudo generar el icono." }

& $python -m PyInstaller --noconfirm --clean CodexUsageMonitor.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }

$exe = Join-Path $root "dist\CodexUsageMonitor\CodexUsageMonitor.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "La build terminó sin generar CodexUsageMonitor.exe."
}

Write-Host "Build ONEDIR creada: $exe"
