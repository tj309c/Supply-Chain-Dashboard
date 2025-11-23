@echo off
REM ----------------------------------------------------------------------------
REM start_dashboard_dev.bat
REM Developer helper: creates/activates a local .venv, installs deps, and runs
REM the Streamlit dashboard in dev mode (opens a browser).
REM
REM Usage:
REM   start_dashboard_dev.bat            -> run dashboard using existing .venv or system python
REM   start_dashboard_dev.bat install    -> create .venv (if missing) and install requirements
REM   start_dashboard_dev.bat run        -> same as no argument (explicit run)
REM   start_dashboard_dev.bat conda=env  -> attempt to activate named conda env instead
REM   start_dashboard_dev.bat env KEY=VALUE ... -> override data file paths (ORDERS, DELIVERIES, MASTER, INVENTORY)
REM Examples:
REM   start_dashboard_dev.bat install
REM   start_dashboard_dev.bat conda=devenv
REM   start_dashboard_dev.bat env ORDERS=data\ORDERS.csv MASTER="C:\\custom\Master Data.csv"
REM ----------------------------------------------------------------------------

setlocal EnableDelayedExpansion

REM Default paths (relative to script dir)
set ROOT=%~dp0
set ORDERS_FILE_PATH=%ROOT%data\ORDERS.csv
set DELIVERIES_FILE_PATH=%ROOT%data\DELIVERIES.csv
set MASTER_DATA_FILE_PATH=%ROOT%data\Master Data.csv
set INVENTORY_FILE_PATH=%ROOT%data\INVENTORY.csv

:parse_args
if "%~1"=="" goto run_app
if /I "%~1"=="run" goto run_app
if /I "%~1"=="install" goto install_venv
if /I "%~1"=="env" goto set_envs

REM Allow passing 'conda=name' as single arg
for /f "tokens=1,2 delims==" %%A in ("%~1") do (
  if /I "%%~A"=="conda" set CONDA_NAME=%%~B
)
if defined CONDA_NAME goto try_conda

echo Unknown argument: %1
echo Usage: start_dashboard_dev.bat ^[install^|run^|conda=name^|env^]
goto end

:set_envs
shift
if "%~1"=="" goto run_app
for %%V in (%*) do (
  for /F "tokens=1* delims==" %%A in ("%%V") do (
    set "k=%%~A"
    set "v=%%~B"
    if /I "!k!"=="ORDERS" set ORDERS_FILE_PATH=!v!
    if /I "!k!"=="DELIVERIES" set DELIVERIES_FILE_PATH=!v!
    if /I "!k!"=="MASTER" set MASTER_DATA_FILE_PATH=!v!
    if /I "!k!"=="INVENTORY" set INVENTORY_FILE_PATH=!v!
  )
)
goto run_app

:install_venv
echo Creating local virtual environment (.venv) and installing requirements...
if not exist "%ROOT%.venv\Scripts\activate" (
  python -m venv "%ROOT%.venv"
  if errorlevel 1 (
    echo Failed to create .venv. Make sure Python is on PATH.
    goto end
  )
)
call "%ROOT%.venv\Scripts\activate"
if errorlevel 1 (
  echo Failed to activate .venv
  goto end
)
if exist "%ROOT%requirements.txt" (
  python -m pip install --upgrade pip
  python -m pip install -r "%ROOT%requirements.txt"
  if errorlevel 1 echo Warning: pip reported errors while installing requirements
) else (
  echo requirements.txt not found at %ROOT%
)
goto end

:try_conda
echo Attempting to activate conda environment: %CONDA_NAME%
REM Using call to keep environment in this session if conda is configured
call conda activate %CONDA_NAME%
if errorlevel 1 (
  echo Failed to activate conda env %CONDA_NAME% - continuing with system python
)
goto run_app

:run_app
REM If .venv exists, activate it
if exist "%ROOT%.venv\Scripts\activate" (
  echo Activating local .venv
  call "%ROOT%.venv\Scripts\activate"
) else (
  echo No local .venv found. Using system Python (consider: start_dashboard_dev.bat install)
)

REM Export environment variables for this CMD session only. Streamlit will read them.
set ORDERS_FILE_PATH=%ORDERS_FILE_PATH%
set DELIVERIES_FILE_PATH=%DELIVERIES_FILE_PATH%
set MASTER_DATA_FILE_PATH=%MASTER_DATA_FILE_PATH%
set INVENTORY_FILE_PATH=%INVENTORY_FILE_PATH%

echo Running dashboard in DEV mode (opens browser). Data files:
echo ORDERS: %ORDERS_FILE_PATH%
echo DELIVERIES: %DELIVERIES_FILE_PATH%
echo MASTER_DATA: %MASTER_DATA_FILE_PATH%
echo INVENTORY: %INVENTORY_FILE_PATH%

REM Run Streamlit in dev mode (not headless)
REM NOTE: `dashboard.py` was removed/legacy. Use `dashboard_simple.py` which is the current app.
python -m streamlit run "%ROOT%dashboard_simple.py" --server.port 8501 --server.headless false
if errorlevel 1 (
  echo Streamlit exited with non-zero status. Try running: python -m streamlit run dashboard.py
)
goto end

:end
endlocal
echo Done.
