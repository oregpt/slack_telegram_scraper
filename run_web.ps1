[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "web")
try {
  if (-not (Test-Path (Join-Path (Get-Location) "node_modules"))) {
    Write-Host "Installing web dependencies..."
    npm install
  }
  Write-Host "Starting Vite dev server..."
  npm run dev
}
finally {
  Pop-Location
}

