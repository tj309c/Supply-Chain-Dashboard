@echo off
REM ----------------------------------------------------------------------------
REM start_dashboard.bat
REM Windows startup helper to install deps (optional), configure data file paths,
REM and run the Streamlit-based Supply Chain Dashboard (dashboard.py).
REM
REM Usage:
REM   start_dashboard.bat              -> runs Streamlit using data/ files (default)
REM   start_dashboard.bat install      -> installs Python requirements
REM   start_dashboard.bat run         -> same as no argument (explicit run)
REM   start_dashboard.bat dev         -> start in development mode (no headless)
REM   start_dashboard.bat env PATHS   -> quickly set data file overrides
REM Examples:
REM   start_dashboard.bat install
REM   start_dashboard.bat env ORDERS=data/ORDERS.csv DELIVERIES=data/DELIVERIES.csv
REM ----------------------------------------------------------------------------

REM --- Quick helper functions -------------------------------------------------
setlocal EnableDelayedExpansion

REM Default file environment variables (edit as needed)
set ORDERS_FILE_PATH=%~dp0data\ORDERS.csv
set DELIVERIES_FILE_PATH=%~dp0data\DELIVERIES.csv
set MASTER_DATA_FILE_PATH=%~dp0data\Master Data.csv
set INVENTORY_FILE_PATH=%~dp0data\INVENTORY.csv

:parse_args
if "%~1"=="" goto run_app
if /I "%~1"=="run" goto run_app
if /I "%~1"=="dev" goto run_dev
if /I "%~1"=="install" goto install_deps
if /I "%~1"=="env" goto set_envs

echo Unknown argument: %1
echo Usage: start_dashboard.bat ^[install^|run^|dev^|env^]
goto end

:set_envs
REM Pass in KEY=VALUE pairs after 'env' to override paths, e.g.
REM   start_dashboard.bat env ORDERS=data\ORDERS.csv MASTER_DATA="C:\path\to\Master Data.csv"
shift
:env_loop
if "%~1"=="" goto run_app
for /F "tokens=1* delims==" %%A in ("%~1") do (
  set "key=%%~A"
  set "val=%%~B"
  if /I "!key!"=="ORDERS" set ORDERS_FILE_PATH=!val!
  if /I "!key!"=="DELIVERIES" set DELIVERIES_FILE_PATH=!val!
  if /I "!key!"=="MASTER" set MASTER_DATA_FILE_PATH=!val!
  if /I "!key!"=="INVENTORY" set INVENTORY_FILE_PATH=!val!
)
shift
goto env_loop

:install_deps
echo Installing Python dependencies from requirements.txt
echo (You can skip this if you already have the virtual environment set up.)
if exist "%~dp0requirements.txt" (
  python -m pip install --upgrade pip
  python -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo Failed to install dependencies. Check python/pip in PATH.
    goto end
  )
) else (
  echo requirements.txt not found in %~dp0
)
goto end

:run_app
REM Auto-install requirements before starting (quick check)
echo Checking and installing dependencies...
if exist "%~dp0requirements.txt" (
  python -m pip install --quiet -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo Warning: Some dependencies may not have installed correctly.
  ) else (
    echo Dependencies installed/verified successfully.
  )
) else (
  echo Warning: requirements.txt not found in %~dp0
)

REM Export environment variables for this CMD session only. Streamlit will read them.
set ORDERS_FILE_PATH=%ORDERS_FILE_PATH%
set DELIVERIES_FILE_PATH=%DELIVERIES_FILE_PATH%
set MASTER_DATA_FILE_PATH=%MASTER_DATA_FILE_PATH%
set INVENTORY_FILE_PATH=%INVENTORY_FILE_PATH%

echo.
echo Starting Supply Chain Dashboard (Streamlit) ...
echo ORDERS: %ORDERS_FILE_PATH%
echo DELIVERIES: %DELIVERIES_FILE_PATH%
echo MASTER_DATA: %MASTER_DATA_FILE_PATH%
echo INVENTORY: %INVENTORY_FILE_PATH%
echo.

REM Prefer using python -m streamlit to avoid PATH issues
python -m streamlit run "%~dp0dashboard_simple.py" --server.port 8501 --server.headless true
if errorlevel 1 (
  echo Streamlit exited with a non-zero status.
  echo Try running: python -m streamlit run dashboard_simple.py
)
goto end

:run_dev
REM Auto-install requirements before starting (quick check)
echo Checking and installing dependencies...
if exist "%~dp0requirements.txt" (
  python -m pip install --quiet -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo Warning: Some dependencies may not have installed correctly.
  ) else (
    echo Dependencies installed/verified successfully.
  )
)

set ORDERS_FILE_PATH=%ORDERS_FILE_PATH%
set DELIVERIES_FILE_PATH=%DELIVERIES_FILE_PATH%
set MASTER_DATA_FILE_PATH=%MASTER_DATA_FILE_PATH%
set INVENTORY_FILE_PATH=%INVENTORY_FILE_PATH%

echo.
echo Starting Dashboard in DEV mode (not headless) ...
python -m streamlit run "%~dp0dashboard_simple.py" --server.port 8501 --server.headless false
goto end

:end
endlocal
echo Done.
