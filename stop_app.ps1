[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Stop-ServerProcs {
  $killed = @()
  try {
    $procs = Get-CimInstance Win32_Process |
      Where-Object {
        ($_.CommandLine -match 'chattools_exporter\.server') -or
        ($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'chattools_exporter\.server')
      }
    foreach ($p in $procs) {
      try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        $killed += $p.ProcessId
      } catch {}
    }
  } catch {}
  return $killed
}

$ids = Stop-ServerProcs
if ($ids.Count -gt 0) {
  Write-Host "Stopped server process IDs: $($ids -join ', ')"
} else {
  Write-Host 'No matching server processes found.'
}

