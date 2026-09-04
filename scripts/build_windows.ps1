$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".build-venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Build environment not found. Create .build-venv and install .[gui] plus pyinstaller first."
}

Push-Location (Join-Path $projectRoot "packaging")
try {
    & $pythonExe -m PyInstaller --noconfirm --clean "stil-to-ni-digital.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$builtExe = Join-Path $projectRoot "packaging\dist\STIL-to-NI-Digital.exe"
& $builtExe --self-test
if ($LASTEXITCODE -ne 0) {
    throw "Packaged executable self-test failed with exit code $LASTEXITCODE"
}

$checksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $builtExe).Hash
$checksumPath = Join-Path $projectRoot "packaging\dist\SHA256SUMS.txt"
Set-Content -LiteralPath $checksumPath -Value "$checksum  STIL-to-NI-Digital.exe" -Encoding ascii

Write-Output $builtExe
Write-Output $checksumPath
