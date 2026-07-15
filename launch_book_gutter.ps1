$ErrorActionPreference = 'Stop'

$projectDir = $PSScriptRoot
Set-Location $projectDir

$appPath = Join-Path $projectDir 'app.py'
$candidates = @(
    (Join-Path $projectDir '.venv\Scripts\python.exe'),
    'C:\Users\drarv\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)

$pythonExe = $null
foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
        $pythonExe = (Resolve-Path $candidate).Path
        break
    }
}

$pythonArgs = @()
if (-not $pythonExe) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExe = 'py'
        $pythonArgs = @('-3')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonExe = 'python'
    }
}

if (-not $pythonExe) {
    Write-Host 'Could not find a Python interpreter.'
    Read-Host 'Press Enter to exit'
    exit 1
}

try {
    & $pythonExe @pythonArgs $appPath
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Book Gutter PDF exited with code $exitCode."
    }
}
catch {
    Write-Host $_
    Read-Host 'Press Enter to exit'
    exit 1
}

exit 0
