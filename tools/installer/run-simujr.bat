@echo off
setlocal

set "APP_DIR=%~dp0"
set "DATA_ROOT=%ProgramData%\SimuJR"
set "ENV_FILE=%DATA_ROOT%\.env"
set "PYTHON_EXE=%APP_DIR%python\python.exe"

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%tools\installer\configure-simujr.ps1" -InstallDir "%APP_DIR%" -DataRoot "%DATA_ROOT%"
if errorlevel 1 (
  echo [ERROR] Failed to configure Simu JR.
  pause
  exit /b 1
)

if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

cd /d "%APP_DIR%"
start "" "http://localhost:8080"
"%PYTHON_EXE%" server.py

if errorlevel 1 (
  echo.
  echo [ERROR] Simu JR stopped with an error.
  pause
)

