@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Interfaz Grafica

rem =====================================================================
rem  ARQ GEN - 08_GUI.bat
rem  Abre la interfaz grafica (spec 90-93): explorador por disciplinas,
rem  lienzo con zoom/pan, edicion de propiedades, buscador y estados.
rem  Ejemplos:
rem     08_GUI.bat                        (abre el proyecto de demostracion)
rem     08_GUI.bat output\mi_proyecto.arqgen
rem     08_GUI.bat --demo
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 08_GUI.bat scripts v1.6.4

call :resolve_py
if not defined PYEXE (
    echo ERROR: no se encontro interprete de Python. Instale Python 3.13
    echo marcando "Add python.exe to PATH", y vuelva a ejecutar este script.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

"%PYEXE%" main.py gui %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo ARQ GEN GUI termino con codigo %RC%. Revise logs\app\errors.log si fue un error inesperado.
    echo.
    if not defined ARQ_NOPAUSE pause
)
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN 08_GUI.bat codigo=%RC%
exit /b %RC%

rem ==================== SUBRUTINAS ====================
:resolve_py
rem Resolvedor de interprete: .venv -> config\python_home.txt -> autodeteccion
set "PYEXE="
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYEXE=%ROOT%\.venv\Scripts\python.exe"
if not defined PYEXE if exist "%ROOT%\config\python_home.txt" set /p PYEXE=<"%ROOT%\config\python_home.txt"
if defined PYEXE if not exist "%PYEXE%" (
    echo [AVISO] El interprete guardado en config\python_home.txt ya no existe: %PYEXE%
    echo [AVISO] Reintentando deteccion automatica...
    set "PYEXE="
)
if defined PYEXE goto resolve_py_check
for %%C in ("py -3.13" "python3.13" "py" "python" "python3") do (
    if not defined PYEXE call :try_candidate %%C
)
:resolve_py_check
if not defined PYEXE goto :eof
rem Validacion final: descarta alias trampa (Microsoft Store) y rutas rotas
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [AVISO] El interprete detectado no responde: %PYEXE%
    set "PYEXE="
)
goto :eof

:try_candidate
rem %1 = candidato entre comillas (puede contener espacios, p.ej. "py -3.13")
set "PYEXE="
for /f "usebackq tokens=*" %%i in (`%~1 -c "import sys;print(sys.executable)" 2^>nul`) do set "PYEXE=%%i"
if not defined PYEXE goto :eof
rem Validacion anti-alias: si no responde, se descarta el candidato
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 set "PYEXE="
goto :eof
