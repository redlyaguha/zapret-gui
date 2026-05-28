$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$DistPath = Join-Path $ProjectRoot "dist"
$SpecPath = Join-Path $ProjectRoot "zapret-gui.spec"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonExe)) {
    python -m venv $VenvPath
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt") pyinstaller

$AppVersion = & $PythonExe -c "from core.app_info import APP_VERSION; print(APP_VERSION)"
$ArchiveName = "zapret-gui-v$AppVersion-windows-x64.zip"
$ArchivePath = Join-Path $DistPath $ArchiveName
$ExePath = Join-Path $DistPath "zapret-gui.exe"

& $PythonExe -m PyInstaller --clean --noconfirm $SpecPath

if (-not (Test-Path $ExePath)) {
    throw "Build failed: $ExePath was not created."
}

if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}

Compress-Archive -Path $ExePath -DestinationPath $ArchivePath
Write-Host "Created $ArchivePath"
