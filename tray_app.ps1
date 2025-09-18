[CmdletBinding()]
param(
  [int]$Port = 8000,
  [switch]$AutoStart = $true
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$root = $PSScriptRoot
$base = "http://localhost:$Port"
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

function Test-Api {
  try { (Invoke-WebRequest -UseBasicParsing "$base/api/health" -TimeoutSec 3) | Out-Null; return $true } catch { return $false }
}

function Ensure-Server {
  # Ensure venv and deps
  if (-not (Test-Path $venvPython)) {
    try {
      py -3 -m venv (Join-Path $root '.venv')
      & $venvPython -m pip install --upgrade pip
      & $venvPython -m pip install -r (Join-Path $root 'requirements.txt')
    } catch {}
  }
  # Build UI if not present
  $dist = Join-Path $root 'web\dist\index.html'
  if (-not (Test-Path $dist)) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
      Push-Location (Join-Path $root 'web')
      try {
        if (-not (Test-Path (Join-Path (Get-Location) 'node_modules'))) { npm install | Out-Null }
        npm run build | Out-Null
      } finally { Pop-Location }
    }
  }
  if (-not (Test-Api)) {
    Start-Process -WindowStyle Hidden powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command', "Set-Location -LiteralPath '$root'; ./run_server.ps1 -Port $Port") | Out-Null
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Api)) {
      Start-Sleep -Seconds 1
      if ((Get-Date) -gt $deadline) { break }
    }
  }
}

function Stop-Server {
  try {
    $procs = Get-CimInstance Win32_Process |
      Where-Object { ($_.CommandLine -match 'chattools_exporter\.server') -or ($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'chattools_exporter\.server') }
    foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
  } catch {}
}

# NotifyIcon setup
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Application
$notify.Visible = $true
$notify.Text = "ChatTools Exporter"

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$openItem  = $menu.Items.Add('Open App')
$startItem = $menu.Items.Add('Start Server')
$stopItem  = $menu.Items.Add('Stop Server')
$exitItem  = $menu.Items.Add('Exit')

$openItem.add_Click({ Start-Process "$base/app" | Out-Null })
$startItem.add_Click({ Ensure-Server; $notify.ShowBalloonTip(2000, 'ChatTools', 'Server is running', [System.Windows.Forms.ToolTipIcon]::Info) })
$stopItem.add_Click({ Stop-Server; $notify.ShowBalloonTip(2000, 'ChatTools', 'Server stopped', [System.Windows.Forms.ToolTipIcon]::Info) })
$exitItem.add_Click({ $notify.Visible = $false; [System.Windows.Forms.Application]::Exit() })

$notify.ContextMenuStrip = $menu
$notify.add_MouseClick({ param($s,$e) if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) { Start-Process "$base/app" | Out-Null } })

if ($AutoStart) {
  Ensure-Server
  Start-Process "$base/app" | Out-Null
}

[System.Windows.Forms.Application]::Run()

