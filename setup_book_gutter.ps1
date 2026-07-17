$ErrorActionPreference = 'Stop'

$projectDir = $PSScriptRoot
Set-Location $projectDir

$venvPython = Join-Path $projectDir '.venv\Scripts\python.exe'

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{ Exe = 'py'; Args = @('-3') }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{ Exe = 'python'; Args = @() }
    }

    return $null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Exe,
        [Parameter(Mandatory = $true)]
        [string[]]$Args,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Exe @Args
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

try {
    $python = Get-PythonCommand
    if (-not $python) {
        throw 'Could not find Python 3. Install Python, then run setup_book_gutter.ps1 again.'
    }

    if (-not (Test-Path $venvPython)) {
        Write-Host 'Creating .venv...'
        Invoke-Checked -Exe $python.Exe -Args ($python.Args + @('-m', 'venv', '.venv')) -FailureMessage 'Failed to create .venv.'
    }

    Write-Host 'Upgrading pip...'
    Invoke-Checked -Exe $venvPython -Args @('-m', 'pip', 'install', '--upgrade', 'pip') -FailureMessage 'Failed to upgrade pip.'

    Write-Host 'Installing project dependencies...'
    Invoke-Checked -Exe $venvPython -Args @('-m', 'pip', 'install', '-r', 'requirements.txt') -FailureMessage 'Failed to install project dependencies.'

    Write-Host 'Verifying PyMuPDF, PySide6, and NumPy...'
    Invoke-Checked -Exe $venvPython -Args @('-c', "import fitz; import PySide6; import numpy; print('Dependency check passed.')") -FailureMessage 'Dependency verification failed.'

    Write-Host ''
    Write-Host 'Setup complete.'
    Write-Host 'Launch the app with:'
    Write-Host 'Book Gutter PDF.bat'
}
catch {
    Write-Host $_
    Read-Host 'Press Enter to exit'
    exit 1
}

exit 0
