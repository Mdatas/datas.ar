<#
.SYNOPSIS
  Installs Datas.ar on Windows 10/11 for the current user. No admin rights needed.

.DESCRIPTION
  1. Finds Python 3.10+ (py launcher, python, or a conda base) or installs Python 3.12 via winget.
  2. Creates a virtual environment in %LOCALAPPDATA%\Datas\app\venv and installs the datas-ar
     wheel found next to this script (or from PyPI).
  3. Writes a launcher (Datas.cmd), Desktop + Start Menu shortcuts and an "Apps & features" entry.
  4. Starts Datas in its own window (no browser, no terminal).

  Run it again to upgrade.  -Uninstall removes the app (downloaded models are kept unless -Purge).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Install-Datas.ps1
  powershell -ExecutionPolicy Bypass -File .\Install-Datas.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$Wheel = "",
    [switch]$Uninstall,
    [switch]$Purge,
    [switch]$NoLaunch,
    [switch]$NoShortcuts
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$DataRoot  = Join-Path $env:LOCALAPPDATA 'Datas'          # models, config, llama.cpp live here (DATAS_HOME)
$AppRoot   = Join-Path $DataRoot 'app'                     # venv + launcher (removed on uninstall)
$Venv      = Join-Path $AppRoot 'venv'
$Launcher  = Join-Path $AppRoot 'Datas.cmd'
$IconPath  = Join-Path $AppRoot 'datas.ico'
$Here      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop   = [Environment]::GetFolderPath('Desktop')
$StartMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$RegKey    = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Datas.ar'

function Step($msg) { Write-Host "-> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
if ($Uninstall) {
    Step "Stopping Datas processes"
    Get-Process -Name 'datas', 'llama-server', 'rpc-server', 'ggml-rpc-server' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Step "Removing app files"
    if (Test-Path $AppRoot) { Remove-Item -Recurse -Force $AppRoot }
    Remove-Item -Force (Join-Path $Desktop 'Datas.ar.lnk') -ErrorAction SilentlyContinue
    Remove-Item -Force (Join-Path $StartMenu 'Datas.ar.lnk') -ErrorAction SilentlyContinue
    Remove-Item -Path $RegKey -Recurse -Force -ErrorAction SilentlyContinue
    if ($Purge) {
        Step "Removing models, config and llama.cpp ($DataRoot)"
        if (Test-Path $DataRoot) { Remove-Item -Recurse -Force $DataRoot }
    } else {
        Warn "Kept your models and config in $DataRoot (use -Purge to delete them too)."
    }
    Ok "Datas.ar uninstalled."
    exit 0
}

# ---------------------------------------------------------------------------
# Python discovery
# ---------------------------------------------------------------------------
function Test-PythonCandidate([string[]]$cmd) {
    try {
        $exe = $cmd[0]
        $rest = @()
        if ($cmd.Length -gt 1) { $rest = $cmd[1..($cmd.Length - 1)] }
        $out = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $lines = @($out)
        if ($lines.Count -lt 2) { return $null }
        $ver = [version]$lines[0]
        if ($ver -ge [version]'3.10') { return $lines[1].Trim() }
    } catch { }
    return $null
}

function Find-Python {
    $candidates = @(
        @('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('py', '-3.10'), @('py', '-3'),
        @('python'), @('python3')
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        $p = Test-PythonCandidate $c
        if ($p) { return $p }
    }
    foreach ($base in @('miniconda3', 'anaconda3', 'Miniconda3', 'Anaconda3')) {
        $exe = Join-Path $env:USERPROFILE "$base\python.exe"
        if (Test-Path $exe) {
            $p = Test-PythonCandidate @($exe)
            if ($p) { return $p }
        }
    }
    return $null
}

function Install-Python {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Warn "Python 3.10+ was not found and winget is not available."
        Warn "Install Python from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then run this installer again."
        Start-Process 'https://www.python.org/downloads/windows/'
        exit 1
    }
    Step "Installing Python 3.12 for this user with winget (one-time, ~30 MB)"
    & winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    # make the new install visible to this session
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Datas.ar - local AI for everyone" -ForegroundColor White
Write-Host "  Installing for $env:USERNAME into $AppRoot" -ForegroundColor DarkGray
Write-Host ""

$py = Find-Python
if (-not $py) { Install-Python; $py = Find-Python }
if (-not $py) { throw "Python 3.10+ still not found. Open a NEW terminal window (PATH refresh) and run the installer again." }
Ok "Python: $py"

New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
$vpy = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    Step "Creating virtual environment"
    & $py -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $vpy)) { throw "Could not create the virtual environment." }
}
Step "Updating pip"
& $vpy -m pip install --quiet --upgrade pip wheel
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

# Where does the package come from? 1) -Wheel  2) a wheel next to this script  3) a source tree next to it  4) PyPI
if (-not $Wheel) {
    $w = Get-ChildItem -Path $Here -Filter 'datas_ar-*.whl' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($w) { $Wheel = $w.FullName }
}
$extras = ''
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { $extras = '[nvidia]'; Ok "NVIDIA GPU detected: installing NVML support" }

if ($Wheel) {
    Step "Installing $([IO.Path]::GetFileName($Wheel))"
    & $vpy -m pip install --quiet --upgrade "$Wheel$extras"
} elseif (Test-Path (Join-Path $Here 'pyproject.toml')) {
    Step "Installing from source tree $Here"
    & $vpy -m pip install --quiet --upgrade "$Here$extras"
} else {
    Step "Installing datas-ar from PyPI"
    & $vpy -m pip install --quiet --upgrade "datas-ar$extras"
}
if ($LASTEXITCODE -ne 0) { throw "pip install failed (see output above)." }
$version = & $vpy -c "import datas; print(datas.__version__)"
Ok "Datas.ar $version installed"

# Launcher
$cmd = @"
@echo off
title Datas.ar
set "DATAS_HOME=%LOCALAPPDATA%\Datas"
"%LOCALAPPDATA%\Datas\app\venv\Scripts\datas.exe" %*
if errorlevel 1 pause
"@
Set-Content -Path $Launcher -Value $cmd -Encoding ASCII
# Windowed launcher: pythonw.exe runs the app with no console window
$PythonW = Join-Path $Venv 'Scripts\pythonw.exe'
$OpenArgs = '-m datas open'

# Icon + copy of this installer (for the uninstall entry)
$srcIcon = Join-Path $Here 'datas.ico'
if (Test-Path $srcIcon) { Copy-Item -Force $srcIcon $IconPath }
Copy-Item -Force $MyInvocation.MyCommand.Path (Join-Path $AppRoot 'Install-Datas.ps1')

# Shortcuts
function New-Shortcut([string]$path, [string]$target, [string]$arguments = '') {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($path)
    $s.TargetPath = $target
    if ($arguments) { $s.Arguments = $arguments }
    $s.WorkingDirectory = Split-Path -Parent $target
    if (Test-Path $IconPath) { $s.IconLocation = "$IconPath,0" }
    $s.Description = 'Datas.ar - local AI for everyone'
    $s.Save()
}
if (-not $NoShortcuts) {
    Step "Creating shortcuts"
    New-Shortcut (Join-Path $Desktop 'Datas.ar.lnk') $PythonW $OpenArgs
    New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null
    New-Shortcut (Join-Path $StartMenu 'Datas.ar.lnk') $PythonW $OpenArgs
}

# Apps & features entry (per-user)
New-Item -Path $RegKey -Force | Out-Null
Set-ItemProperty -Path $RegKey -Name 'DisplayName' -Value 'Datas.ar'
Set-ItemProperty -Path $RegKey -Name 'DisplayVersion' -Value "$version"
Set-ItemProperty -Path $RegKey -Name 'Publisher' -Value 'Datas.ar contributors'
Set-ItemProperty -Path $RegKey -Name 'InstallLocation' -Value $AppRoot
Set-ItemProperty -Path $RegKey -Name 'DisplayIcon' -Value $IconPath
Set-ItemProperty -Path $RegKey -Name 'NoModify' -Value 1 -Type DWord
Set-ItemProperty -Path $RegKey -Name 'NoRepair' -Value 1 -Type DWord
Set-ItemProperty -Path $RegKey -Name 'UninstallString' -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$AppRoot\Install-Datas.ps1`" -Uninstall"

# PATH hint (optional): add the venv Scripts dir so `datas` works in any terminal
$scripts = Join-Path $Venv 'Scripts'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$scripts*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$scripts", 'User')
    Ok "Added to your PATH: open a new terminal and type 'datas' for the CLI"
}

Write-Host ""
Ok "Done. Shortcut 'Datas.ar' is on your Desktop and Start Menu."
Write-Host "    Models, config and llama.cpp go to $DataRoot" -ForegroundColor DarkGray
Write-Host "    Uninstall: Settings > Apps > Datas.ar, or run this script with -Uninstall" -ForegroundColor DarkGray
Write-Host ""

if (-not $NoLaunch) {
    Step "Starting Datas.ar (first run downloads llama.cpp, ~30-200 MB depending on your GPU)"
    $env:DATAS_HOME = $DataRoot
    Start-Process -FilePath $PythonW -ArgumentList $OpenArgs -WorkingDirectory $AppRoot
}
