@echo off
REM Launcher for the MH Save Converter Pipeline (Windows).
REM Ensures a local .venv with the Python deps, then runs the app.
REM Rust / save3ds are built from the app's [4] Install Dependencies menu.
setlocal enableextensions
cd /d "%~dp0"

set "VENV=.venv"
set "LOCK=%VENV%\.requirements.lock"
set "CONVERTER=MHXXGUSaveConvert\MHGU-MHXX-Save-Converter-Script\modules\converter_api.py"

REM 1. Pick a Python interpreter (py launcher preferred, then python).
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Error: Python 3 not found. Install Python 3.8+ from https://python.org and try again.
  goto :end
)

REM 2. Initialize submodules if the converter is missing (only in a git checkout).
if not exist "%CONVERTER%" (
  if exist ".git" (
    echo Initializing git submodules...
    git submodule update --init
  )
)

REM 3. Create the virtual environment if needed.
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating virtual environment in %VENV% ...
  %PY% -m venv "%VENV%"
  if errorlevel 1 ( echo Failed to create virtual environment. & goto :end )
)
set "VPY=%VENV%\Scripts\python.exe"

REM 4. (Re)install requirements when they change (stamp compare).
set "NEED_INSTALL=0"
if not exist "%LOCK%" (
  set "NEED_INSTALL=1"
) else (
  fc /b requirements.txt "%LOCK%" >nul 2>&1 || set "NEED_INSTALL=1"
)
if "%NEED_INSTALL%"=="1" (
  echo Installing Python dependencies ...
  "%VPY%" -m pip install --upgrade pip >nul 2>&1
  "%VPY%" -m pip install -r requirements.txt
  if errorlevel 1 ( echo pip install failed. & goto :end )
  copy /y requirements.txt "%LOCK%" >nul
)

REM 5. Launch the app (forward any extra arguments).
"%VPY%" -m mhpipeline %*

:end
echo.
pause
endlocal
