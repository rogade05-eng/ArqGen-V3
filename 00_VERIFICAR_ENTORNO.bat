@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Verificacion del entorno

rem =====================================================================
rem  ARQ GEN - 00_VERIFICAR_ENTORNO.bat
rem  Detecta Python 3.13 en el equipo y guarda la RUTA COMPLETA del
rem  interprete elegido en config\python_home.txt. Registra todo en
rem  logs\setup\.
rem  Orden de busqueda: py -3.13 -> python3.13 -> py -> python -> python3
rem  Override manual: defina ARQ_PY_EXE con la ruta completa de python.exe
rem  Automation: defina ARQ_NOPAUSE=1 para desactivar las pausas.
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 00_VERIFICAR_ENTORNO.bat scripts v1.6.4

for /f "usebackq" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%i"
if not defined STAMP set "STAMP=%RANDOM%%RANDOM%"
set "LOG=logs\setup\env_%STAMP%.log"
set "CFG=config"

if not exist "%CFG%" mkdir "%CFG%"
if not exist logs\setup mkdir logs\setup

>>"%LOG%" echo ============================================================
>>"%LOG%" echo [%DATE% %TIME%] ARQ GEN - Verificacion de entorno
>>"%LOG%" echo ============================================================
echo Verificando entorno de ARQ GEN...
echo Detalle completo en: %LOG%

rem --- 1) Override manual -------------------------------------------------
if defined ARQ_PY_EXE (
    >>"%LOG%" echo [INFO] Usando ARQ_PY_EXE definido por el usuario: %ARQ_PY_EXE%
    if not exist "%ARQ_PY_EXE%" (
        >>"%LOG%" echo [ERROR] ARQ_PY_EXE apunta a un archivo inexistente.
        echo ERROR: la ruta indicada en ARQ_PY_EXE no existe.
        type "%LOG%"
        echo.
        if not defined ARQ_NOPAUSE pause
        exit /b 1
    )
    set "PYEXE=%ARQ_PY_EXE%"
    goto check_version
)

rem --- 2) Buscar candidatos ----------------------------------------------
set "PYEXE="
for %%C in ("py -3.13" "python3.13" "py" "python" "python3") do (
    if not defined PYEXE call :try_candidate %%C
)
if defined PYEXE >>"%LOG%" echo [INFO] Interprete seleccionado: %PYEXE%

if not defined PYEXE (
    >>"%LOG%" echo [ERROR] No se encontro Python en el sistema.
    echo ============================================================
    type "%LOG%"
    echo.
    echo ERROR: Python no encontrado. Instale Python 3.13 desde
    echo https://www.python.org/downloads/ y marque "Add python.exe to PATH"
    echo o defina la variable ARQ_PY_EXE con la ruta completa del interprete.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

:check_version
rem --- 3) Verificar version ------------------------------------------------
set "PYVER="
for /f "usebackq tokens=*" %%v in (`"%PYEXE%" -c "import sys;print(str(sys.version_info[0])+'.'+str(sys.version_info[1]))" 2^>nul`) do set "PYVER=%%v"
if not defined PYVER (
    >>"%LOG%" echo [ERROR] El interprete %PYEXE% no responde correctamente.
    echo ERROR: el interprete no responde. Revise el log: %LOG%
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
>>"%LOG%" echo [INFO] Version detectada: %PYVER%
echo Version de Python: %PYVER%

echo %PYVER%| findstr /b /c:"3.13" >nul
if errorlevel 1 (
    >>"%LOG%" echo [AVISO] La especificacion ARQ GEN requiere Python 3.13; se detecto %PYVER%.
    if not defined ARQ_ALLOW_OTHER_PYTHON (
        echo ============================================================
        type "%LOG%"
        echo.
        echo ERROR: se requiere Python 3.13 y se encontro %PYVER%.
        echo Instale Python 3.13, o ejecute de nuevo con:
        echo     set ARQ_ALLOW_OTHER_PYTHON=1
        echo Tambien puede fijar ARQ_PY_EXE a la ruta exacta del interprete.
        echo.
        if not defined ARQ_NOPAUSE pause
        exit /b 1
    )
)

rem --- 4) Guardar eleccion (ruta completa; el resto de los .bat la cita) ---
>"%CFG%\python_home.txt" echo %PYEXE%
>>"%LOG%" echo [INFO] Interprete guardado en %CFG%\python_home.txt
>>"%LOG%" echo [INFO] Comprobando biblioteca estandar (sqlite3, json, logging, unittest, tkinter)...
"%PYEXE%" -c "import sqlite3, json, logging, unittest, tkinter; print('stdlib OK')" >> "%LOG%" 2>&1
if errorlevel 1 (
    >>"%LOG%" echo [ERROR] La biblioteca estandar no responde correctamente.
    type "%LOG%"
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

echo.
echo ============================================================
echo  ENTORNO VERIFICADO CORRECTAMENTE
echo  Interprete : %PYEXE%  (Python %PYVER%)
echo  Registro   : %LOG%
echo ============================================================
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN OK 00_VERIFICAR_ENTORNO.bat
endlocal
exit /b 0

rem ==================== SUBRUTINAS ====================

:try_candidate
rem %1 = candidato entre comillas (puede contener espacios, p.ej. "py -3.13")
set "PYEXE="
for /f "usebackq tokens=*" %%i in (`%~1 -c "import sys;print(sys.executable)" 2^>nul`) do set "PYEXE=%%i"
if not defined PYEXE goto :eof
rem Validacion anti-alias: si no responde, se descarta el candidato
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 set "PYEXE="
goto :eof
