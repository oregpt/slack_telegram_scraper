[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

# Ensure venv exists
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment (.venv) and installing dependencies..."
    py -3 -m venv (Join-Path $PSScriptRoot ".venv")
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
}

# Run exporter module from src package
$env:PYTHONPATH = (Join-Path $PSScriptRoot "src")
& $venvPython -m chattools_exporter.export_telegram @Args
