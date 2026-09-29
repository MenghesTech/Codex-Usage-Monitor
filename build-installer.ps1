$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$portable = Join-Path $root "dist\CodexUsageMonitor"
$portableExe = Join-Path $portable "CodexUsageMonitor.exe"
$script = Join-Path $root "installer\CodexUsageMonitor.iss"
$output = Join-Path $root "installer\output\CodexUsageMonitor-Setup-v1.0.0.exe"

if (-not (Test-Path -LiteralPath $portableExe -PathType Leaf)) {
    throw "Falta la build portable v1.0.0: $portableExe. Ejecuta build.ps1 primero."
}
if ((Get-Item -LiteralPath $portableExe).VersionInfo.ProductVersion -ne "1.0.0") {
    throw "La build portable no tiene ProductVersion 1.0.0. No se reutilizara otro binario."
}
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "No existe el script Inno Setup: $script"
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
)
$isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($isccCommand) { $isccCandidates = @($isccCommand.Source) + $isccCandidates }
$iscc = $isccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup no está instalado. Instálalo desde https://jrsoftware.org/isdl.php y vuelve a ejecutar este script."
}

if (Test-Path -LiteralPath $output) {
    $resolvedOutput = (Resolve-Path -LiteralPath $output).Path
    if (-not $resolvedOutput.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta de limpieza insegura: $resolvedOutput"
    }
    Remove-Item -LiteralPath $resolvedOutput -Force
}

& $iscc $script
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló con código $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw "Inno Setup terminó sin generar el instalador esperado: $output"
}

Write-Host "Instalador creado: $output"
