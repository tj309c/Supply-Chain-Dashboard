<#
.SYNOPSIS
  Windows PowerShell helper to run the Streamlit Supply Chain Dashboard (dashboard.py).

.DESCRIPTION
  This script closely mirrors start_dashboard.bat with PowerShell-friendly
  patterns and extra support to auto-activate a local venv (.venv / venv) or a
  named conda environment when requested.

.USAGE
  # Run the dashboard (headless)
  pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run

  # Run in dev mode (open browser / not headless)
  pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Dev

  # Install dependencies from requirements.txt
  pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Install

  # Set environment variables (one or more KEY=VALUE). Keys: ORDERS, DELIVERIES, MASTER, INVENTORY
  pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Env -EnvVars "ORDERS=data\ORDERS.csv","MASTER=C:\data\Master Data.csv"

  # Try to auto-activate a local venv before running (looks for .venv, venv, env)
  pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run -AutoActivateVenv $true

  # Activate a conda env by name (only if conda is available in PATH)
  pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run -CondaName myenv

.NOTES
  - This script runs within its own PowerShell session; activating a venv here
    will not automatically activate it in a separate interactive shell.
  - Use `-ExecutionPolicy Bypass` when running from an untrusted environment.
#>

param(
    [ValidateSet("Install","Run","Dev","Env","Help")]
    [string]$Action = "Run",

    [string[]]$EnvVars = @(),          # KEY=VALUE pairs (e.g. ORDERS=path)

    [switch]$AutoActivateVenv,         # If set, attempt to activate .venv/venv/env
    [string]$CondaName                 # Optionally activate a named conda env
)

function Write-Info { param($m) Write-Host "[INFO] $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red }

Set-StrictMode -Version Latest

# Default file paths (relative to script dir)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$env:ORDERS_FILE_PATH = $env:ORDERS_FILE_PATH -or (Join-Path $ScriptDir 'data\ORDERS.csv')
$env:DELIVERIES_FILE_PATH = $env:DELIVERIES_FILE_PATH -or (Join-Path $ScriptDir 'data\DELIVERIES.csv')
$env:MASTER_DATA_FILE_PATH = $env:MASTER_DATA_FILE_PATH -or (Join-Path $ScriptDir 'data\Master Data.csv')
$env:INVENTORY_FILE_PATH = $env:INVENTORY_FILE_PATH -or (Join-Path $ScriptDir 'data\INVENTORY.csv')

function Show-Help {
    Write-Host "start_dashboard.ps1 - PowerShell helper to run the Streamlit dashboard`n"
    Write-Host "Usage examples:"
    Write-Host "  Install deps:     pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Install"
    Write-Host "  Run (headless):   pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run"
    Write-Host "  Run (dev):        pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Dev"
    Write-Host "  Set envs:         pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Env -EnvVars \"ORDERS=data\\ORDERS.csv\""
    Write-Host "  Auto-activate venv: pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run -AutoActivateVenv`n"
}

if ($Action -eq 'Help') { Show-Help; exit 0 }

if ($Action -eq 'Install') {
    if (Test-Path (Join-Path $ScriptDir 'requirements.txt')) {
        Write-Info 'Installing Python dependencies (requirements.txt)'
        & python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { Write-Warn 'pip upgrade failed (ok to continue)'}
        & python -m pip install -r (Join-Path $ScriptDir 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { Write-Err 'Failed installing requirements. Ensure Python & pip are on PATH.'; exit 1 }
    } else {
        Write-Warn "requirements.txt not found in $ScriptDir"
    }
    exit 0
}

# Parse and set environment variable overrides
if ($Action -eq 'Env') {
    if (-not $EnvVars -or $EnvVars.Count -eq 0) { Write-Warn 'No env vars provided (e.g. ORDERS=path)'; exit 1 }
    foreach ($pair in $EnvVars) {
        if ($pair -notmatch '=') { Write-Warn "Skipping malformed pair: $pair"; continue }
        $k,$v = $pair -split '=',2
        switch ($k.ToUpper()) {
            'ORDERS'     { $env:ORDERS_FILE_PATH = $v }
            'DELIVERIES' { $env:DELIVERIES_FILE_PATH = $v }
            'MASTER'     { $env:MASTER_DATA_FILE_PATH = $v }
            'INVENTORY'  { $env:INVENTORY_FILE_PATH = $v }
            default      { Write-Warn "Unknown key: $k - setting env var directly"; Set-Item -Path "env:$k" -Value $v }
        }
        Write-Info "Set $k -> $v"
    }
    Write-Info 'Environment variables updated for this session (effective only in this process)'
    exit 0
}

# Helper: attempt to activate local venv (PowerShell)
function Try-Activate-Venv {
    $candidates = @(Join-Path $ScriptDir '.venv\Scripts\Activate.ps1'),
                  @(Join-Path $ScriptDir 'venv\Scripts\Activate.ps1'),
                  @(Join-Path $ScriptDir 'env\Scripts\Activate.ps1')

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            Write-Info "Activating virtualenv: $path"
            try { & $path; return $true } catch { Write-Warn "Failed to activate $path - $_"; continue }
        }
    }
    return $false
}

# Ensure venv exists (create it if missing) and return python executable path
function Ensure-LocalVenv {
    param(
        [string]$VenvName = '.venv'
    )

    $venvRoot = Join-Path $ScriptDir $VenvName
    $venvPy = Join-Path $venvRoot 'Scripts\python.exe'

    if (-not (Test-Path $venvRoot)) {
        Write-Info "Local venv not found at $venvRoot — creating .venv using system python"
        # Create venv
        $cmd = & python -m venv $venvRoot
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Failed to create virtualenv at $venvRoot -- continuing without venv"
            return $null
        }
        Write-Info "Virtualenv created at $venvRoot"
    }

    if (Test-Path $venvPy) { return $venvPy }
    return $null
}

# Install requirements into a given python interpreter
function Install-Requirements($pythonExe) {
    if (-not (Test-Path (Join-Path $ScriptDir 'requirements.txt'))) {
        Write-Warn 'No requirements.txt found to install'
        return
    }
    Write-Info "Installing requirements into $pythonExe"
    & $pythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Write-Warn 'pip upgrade failed (ok to continue)' }
    & $pythonExe -m pip install -r (Join-Path $ScriptDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Write-Warn 'pip install -r requirements.txt reported errors' }
}

# Helper: try to activate a named conda env if conda is installed
function Try-Activate-Conda($name) {
    if (-not $name) { return $false }
    # Test conda existence
    try {
        $condaPath = Get-Command conda -ErrorAction Stop
    } catch { Write-Warn 'conda not on PATH; skipping conda activation'; return $false }

    Write-Info "Attempting to conda activate $name"
    # Use conda activate in this process; requires conda PowerShell integration
    try {
        & conda activate $name
        if ($LASTEXITCODE -eq 0) { return $true }
    } catch { Write-Warn "conda activation failed: $_" }
    return $false
}

# If requested, try auto activation (create venv if missing, install reqs, then activate)
if ($AutoActivateVenv.IsPresent) {
    # Try to activate an existing venv first
    $activated = Try-Activate-Venv

    if (-not $activated) {
        # Ensure a local venv exists
        $localPython = Ensure-LocalVenv -VenvName '.venv'
        if ($localPython) {
            # Install requirements into the local venv
            Install-Requirements -pythonExe $localPython
            # Try activating again (Activate.ps1 should now exist)
            $activated = Try-Activate-Venv
            if (-not $activated) { Write-Warn 'Could not activate the newly-created venv; continuing with system python.' }
        } else {
            Write-Warn 'No local venv created or found; continuing with system python.'
        }
    }

    # If activation not successful and a conda name was provided, try conda
    if (-not $activated -and $CondaName) { $activated = Try-Activate-Conda $CondaName }
    if (-not $activated -and $CondaName) { Write-Warn "Conda activation requested but not successful (name: $CondaName)" }
}

# Kill any existing processes using port 8501
Write-Info 'Checking for existing Streamlit processes on port 8501...'
try {
    $processes = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $processes) {
        Write-Info "Closing existing process on port 8501 (PID: $pid)"
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Warn "Could not check for existing processes: $_"
}

# Show current runtime file settings
Write-Host "ORDERS: $env:ORDERS_FILE_PATH"
Write-Host "DELIVERIES: $env:DELIVERIES_FILE_PATH"
Write-Host "MASTER_DATA: $env:MASTER_DATA_FILE_PATH"
Write-Host "INVENTORY: $env:INVENTORY_FILE_PATH`n"

switch ($Action) {
    'Run' {
        # Auto-check and install requirements
        Write-Info 'Checking and installing dependencies...'
        if (Test-Path (Join-Path $ScriptDir 'requirements.txt')) {
            & python -m pip install --quiet -r (Join-Path $ScriptDir 'requirements.txt')
            if ($LASTEXITCODE -eq 0) {
                Write-Info 'Dependencies installed/verified successfully.'
            } else {
                Write-Warn 'Some dependencies may not have installed correctly.'
            }
        }

        Write-Info 'Launching Streamlit (headless)'
        & python -m streamlit run (Join-Path $ScriptDir 'dashboard_simple.py') --server.port 8501 --server.headless true
        if ($LASTEXITCODE -ne 0) { Write-Err 'Streamlit exited with an error. Try running manually.'; exit $LASTEXITCODE }
    }
    'Dev' {
        # Auto-check and install requirements
        Write-Info 'Checking and installing dependencies...'
        if (Test-Path (Join-Path $ScriptDir 'requirements.txt')) {
            & python -m pip install --quiet -r (Join-Path $ScriptDir 'requirements.txt')
            if ($LASTEXITCODE -eq 0) {
                Write-Info 'Dependencies installed/verified successfully.'
            } else {
                Write-Warn 'Some dependencies may not have installed correctly.'
            }
        }

        Write-Info 'Launching Streamlit (dev mode: not headless)'
        & python -m streamlit run (Join-Path $ScriptDir 'dashboard_simple.py') --server.port 8501 --server.headless false
        if ($LASTEXITCODE -ne 0) { Write-Err 'Streamlit exited with an error. Try running manually.'; exit $LASTEXITCODE }
    }
    default {
        Write-Warn "Unhandled action: $Action; use -Action Help for usage"
        Show-Help
        exit 1
    }
}

Write-Host "`nDone."
