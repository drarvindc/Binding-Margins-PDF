$ErrorActionPreference = 'Stop'

$projectDir = $PSScriptRoot
Set-Location $projectDir

$appPath = Join-Path $projectDir 'app.py'
$venvPython = Join-Path $projectDir '.venv\Scripts\python.exe'

function Show-SetupMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host $Message
    Write-Host 'Please run setup_book_gutter.bat first.'
    Read-Host 'Press Enter to exit'
    exit 1
}

if (-not (Test-Path $venvPython)) {
    Show-SetupMessage 'Book Gutter PDF is not set up yet.'
}

& $venvPython -c "import fitz; import PySide6; import numpy"
if ($LASTEXITCODE -ne 0) {
    Show-SetupMessage 'Book Gutter PDF is set up, but dependencies are missing.'
}

& $venvPython $appPath
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host "Book Gutter PDF exited with code $exitCode."
    Read-Host 'Press Enter to exit'
    exit $exitCode
}

exit 0
