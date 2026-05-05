<#
.SYNOPSIS
Stop the local Flask project server for this repository.

.DESCRIPTION
Finds Python processes that are running this project's app.py and stops them.
By default the script is conservative: it only targets command lines that contain
the absolute app.py path for this repository. Use -ByPort to additionally stop
the process listening on the configured port, after showing what it matched.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\stop-project.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\stop-project.ps1 -DryRun

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\stop-project.ps1 -ByPort
#>

param(
    [int]$Port = 5000,
    [switch]$ByPort,
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AppPath = (Join-Path $ProjectRoot 'app.py')
$EscapedAppPath = [regex]::Escape($AppPath)

function Get-ProjectPythonProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match '^(python|pythonw)\.exe$' -and
            $_.CommandLine -and
            ($_.CommandLine -match $EscapedAppPath -or $_.CommandLine -match '(^|\s)app\.py(\s|$)')
        } |
        Where-Object {
            # Keep the fallback app.py match scoped to this repository when possible.
            $_.CommandLine -match $EscapedAppPath -or $_.CommandLine -match [regex]::Escape($ProjectRoot)
        }
}

function Get-PortOwningProcessId {
    param([int]$TargetPort)

    $connections = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    $connections | Select-Object -ExpandProperty OwningProcess -Unique
}

$targets = @()
$targets += Get-ProjectPythonProcesses

if ($ByPort) {
    foreach ($processId in Get-PortOwningProcessId -TargetPort $Port) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($proc) {
            $targets += $proc
        }
    }
}

$targets = $targets | Sort-Object ProcessId -Unique

if (-not $targets -or $targets.Count -eq 0) {
    Write-Host "No matching project server process found. Project root: $ProjectRoot; port: $Port"
    exit 0
}

Write-Host "Matched project server process(es):"
foreach ($proc in $targets) {
    Write-Host ("- PID {0}: {1}" -f $proc.ProcessId, $proc.CommandLine)
}

if ($DryRun) {
    Write-Host "DryRun enabled: no process was stopped."
    exit 0
}

foreach ($proc in $targets) {
    try {
        if ($Force) {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } else {
            Stop-Process -Id $proc.ProcessId -ErrorAction Stop
        }
        Write-Host ("Stopped PID {0}" -f $proc.ProcessId)
    } catch {
        Write-Warning ("Failed to stop PID {0}: {1}" -f $proc.ProcessId, $_.Exception.Message)
    }
}
