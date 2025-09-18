[CmdletBinding()]
param(
    [int]$Port = 8000,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment (.venv) and installing dependencies..."
    py -3 -m venv (Join-Path $PSScriptRoot ".venv")
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
}

$env:PYTHONPATH = (Join-Path $PSScriptRoot "src")
$env:EXPORTER_PORT = "$Port"
& $venvPython -m chattools_exporter.server @Args

