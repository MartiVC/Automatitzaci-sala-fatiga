@echo off
REM ============================================================================
REM  run_app_service.bat
REM
REM  Wrapper per arrencar l'app Qt del PC LAB com a tasca programada de Windows
REM  (Task Scheduler). Deriva la ruta del repositori a partir de la pròpia
REM  ubicació d'aquest script, de manera que funciona allà on copiïs el repo.
REM
REM  Redirigeix stdout/stderr a logs\run_app_stdout.log perquè quedin
REM  capturats els errors que succeeixin ABANS que el logger Python s'arrenqui
REM  (problemes de venv, dependències, config corrupta...).
REM ============================================================================

setlocal

REM %~dp0 és el directori d'aquest .bat (acabat amb \). Pujant un nivell
REM arribem a l'arrel del repositori.
set "REPO_DIR=%~dp0.."
pushd "%REPO_DIR%" || exit /b 1

if not exist "logs" mkdir "logs"

REM Trobar Python: primer venv del repo, si no hi és cau al python del PATH.
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [run_app_service] ERROR: no s'ha trobat ni .venv\Scripts\python.exe ni python al PATH >> "logs\run_app_stdout.log"
        popd
        exit /b 2
    )
    set "PY=python"
)

echo. >> "logs\run_app_stdout.log"
echo [run_app_service] === arrencada %DATE% %TIME% (python=%PY%) === >> "logs\run_app_stdout.log"

"%PY%" run_app.py --start >> "logs\run_app_stdout.log" 2>&1
set "RC=%ERRORLEVEL%"

echo [run_app_service] === sortida amb codi %RC% el %DATE% %TIME% === >> "logs\run_app_stdout.log"

popd
endlocal & exit /b %RC%
