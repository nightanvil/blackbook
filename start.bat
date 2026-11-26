@echo off
rem Start blackbook on Windows. The first start sets everything up inside this folder.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\blackbook.exe" echo First start: setting up blackbook inside this folder. This takes a few minutes and needs internet.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bootstrap.py --if-needed || goto :failed
    goto :run
)

rem The py launcher and a real python.exe both work; the Microsoft Store alias does not
py -3 --version >nul 2>&1 && ( py -3 bootstrap.py --if-needed || goto :failed ) && goto :run
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>&1 && ( python bootstrap.py --if-needed || goto :failed ) && goto :run

rem No Python on this computer: fetch uv, which brings its own Python, into .tools
echo Python not found, downloading a private copy into this folder ...
set "UV_VERSION=0.5.11"
set "UV_PYTHON_INSTALL_DIR=%~dp0.tools\python"
set "UV_CACHE_DIR=%~dp0.tools\cache"
set "UV_PYTHON_PREFERENCE=only-managed"
if not exist ".tools\uv\uv.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = Stop; $zip = Join-Path $env:TEMP blackbook-uv.zip; Invoke-WebRequest https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip -OutFile $zip; New-Item -ItemType Directory -Force .tools\uv | Out-Null; Expand-Archive $zip -DestinationPath .tools\uv -Force; Remove-Item $zip" || goto :failed
)
".tools\uv\uv.exe" run --no-project --python 3.12 bootstrap.py --if-needed || goto :failed

:run
".venv\Scripts\blackbook.exe" %*
if errorlevel 1 goto :failed
goto :eof

:failed
echo.
echo blackbook could not start, see the messages above.
pause
exit /b 1
