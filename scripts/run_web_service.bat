@echo off
REM ============================================================================
REM  run_web_service.bat
REM
REM  Wrapper per arrencar el dashboard FastAPI del PC LAB com a tasca
REM  programada de Windows (Task Scheduler). Pot arrencar sense usuari logat.
REM
REM  El host/port els llegeix del config.yaml. Si vols sobreescriure'ls,
REM  modifica la línia del 'python run_web.py' afegint-hi --host / --port.
REM ============================================================================

setlocal

set "REPO_DIR=%~dp0.."
pushd "%REPO_DIR%" || exit /b 1

if not exist "logs" mkdir "logs"

REM Trobar Python: primer venv del repo, si no hi és cau al python del PATH.
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [run_web_service] ERROR: no s'ha trobat ni .venv\Scripts\python.exe ni python al PATH >> "logs\run_web_stdout.log"
        popd
        exit /b 2
    )
    set "PY=python"
)

echo. >> "logs\run_web_stdout.log"
echo [run_web_service] === arrencada %DATE% %TIME% (python=%PY%) === >> "logs\run_web_stdout.log"

"%PY%" run_web.py >> "logs\run_web_stdout.log" 2>&1
set "RC=%ERRORLEVEL%"

echo [run_web_service] === sortida amb codi %RC% el %DATE% %TIME% === >> "logs\run_web_stdout.log"

popd
endlocal & exit /b %RC%
