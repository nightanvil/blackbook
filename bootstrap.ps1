# Sets up the complete toolchain inside the repository (Windows, PowerShell 5.1 or 7).
# Usage: .\bootstrap.ps1 [-Dev] [-Clean]
param (
    [switch] $Dev,
    [switch] $Clean
)

$ErrorActionPreference = 'Stop'

$uv_version     = '0.5.11'
$python_version = '3.12'

$repo_dir  = $PSScriptRoot
$tools_dir = Join-Path $repo_dir '.tools'
$venv_dir  = Join-Path $repo_dir '.venv'

$env:UV_INSTALL_DIR        = Join-Path $tools_dir 'uv'
$env:UV_NO_MODIFY_PATH     = '1'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $tools_dir 'python'
$env:UV_CACHE_DIR          = Join-Path $tools_dir 'cache'
$env:UV_PYTHON_PREFERENCE  = 'only-managed'

$uv_bin     = Join-Path $env:UV_INSTALL_DIR 'uv.exe'
$venv_python = Join-Path $venv_dir 'Scripts\python.exe'

if ( $Clean ) {
    Write-Host "Removing $tools_dir and $venv_dir"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tools_dir, $venv_dir
}

New-Item -ItemType Directory -Force -Path $tools_dir | Out-Null

# uv
$install_uv = $true
if ( Test-Path $uv_bin ) {
    $installed_version = ( & $uv_bin --version ).Split(' ')[1]
    if ( $installed_version -eq $uv_version ) {
        $install_uv = $false
    }
}
if ( $install_uv ) {
    Write-Host "Installing uv $uv_version into $env:UV_INSTALL_DIR"
    $installer = Invoke-RestMethod "https://astral.sh/uv/$uv_version/install.ps1"
    Invoke-Expression $installer
}

# Python and virtual environment
& $uv_bin python install $python_version
if ( $LASTEXITCODE -ne 0 ) { throw 'uv python install failed' }

if ( -not ( Test-Path $venv_python ) ) {
    & $uv_bin venv $venv_dir --python $python_version
    if ( $LASTEXITCODE -ne 0 ) { throw 'uv venv failed' }
}

# Dependencies
$requirements = Join-Path $repo_dir 'requirements.txt'
if ( $Dev ) {
    $requirements = Join-Path $repo_dir 'requirements-dev.txt'
}
& $uv_bin pip install --python $venv_python -r $requirements
if ( $LASTEXITCODE -ne 0 ) { throw 'uv pip install failed' }

Write-Host ''
Write-Host "Done. Python: $( & $venv_python --version )"
Write-Host 'Activate with: .\.venv\Scripts\Activate.ps1'
