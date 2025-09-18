[CmdletBinding()]
param(
  [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

Write-Host "== ChatTools Exporter: Starting local app =="

# Ensure venv and deps
if (-not (Test-Path $venvPython)) {
  Write-Host 'Creating virtual environment and installing Python deps...'
  py -3 -m venv (Join-Path $root '.venv')
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install -r (Join-Path $root 'requirements.txt')
}

# Build web if needed
$dist = Join-Path $root 'web\dist\index.html'
if (-not (Test-Path $dist)) {
  $npm = Get-Command npm -ErrorAction SilentlyContinue
  if ($npm) {
    Push-Location (Join-Path $root 'web')
    try {
      if (-not (Test-Path (Join-Path (Get-Location) 'node_modules'))) {
        Write-Host 'Installing web dependencies...'
        npm install | Out-Host
      }
      Write-Host 'Building web app...'
      npm run build | Out-Host
    } finally { Pop-Location }
  } else {
    Write-Warning 'web/dist missing and npm not found. UI may be unavailable until you run ./run_web_build.ps1'
  }
}

# Start server if not running
$base = "http://localhost:$Port"
function Test-Api {
  try { (Invoke-WebRequest -UseBasicParsing "$base/api/health" -TimeoutSec 3) | Out-Null; return $true } catch { return $false }
}

if (-not (Test-Api)) {
  Write-Host "Starting API server on port $Port..."
  Start-Process -WindowStyle Hidden powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command', "Set-Location -LiteralPath '$root'; ./run_server.ps1 -Port $Port") | Out-Null
  $deadline = (Get-Date).AddSeconds(30)
  while (-not (Test-Api)) {
    Start-Sleep -Seconds 1
    if ((Get-Date) -gt $deadline) { throw 'Server did not become healthy in time.' }
  }
}

# Open browser
$appUrl = "$base/app"
Write-Host "Opening $appUrl ..."
Start-Process $appUrl | Out-Null
Write-Host 'Ready. Close this window if not needed.'

