@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Pruebas unitarias

rem =====================================================================
rem  ARQ GEN - 02_PRUEBAS.bat
rem  Ejecuta la suite completa de pruebas (unittest) y guarda el
rem  resultado en logs\tests\run_<fecha>.log
rem  Codigo de salida 0 = todas pasan; 1 = hay fallos.
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 02_PRUEBAS.bat scripts v1.6.4

if not exist logs\tests mkdir logs\tests
for /f "usebackq" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%i"
if not defined STAMP set "STAMP=%RANDOM%%RANDOM%"
set "LOG=logs\tests\run_%STAMP%.log"

call :resolve_py
if not defined PYEXE (
    echo ERROR: no se encontro interprete de Python. Instale Python 3.13
    echo marcando "Add python.exe to PATH", y vuelva a ejecutar este script.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

>>"%LOG%" echo ============================================================
>>"%LOG%" echo [%DATE% %TIME%] ARQ GEN - Suite de pruebas
>>"%LOG%" echo ============================================================
>>"%LOG%" echo Interprete: %PYEXE%
echo Ejecutando pruebas ARQ GEN ...
echo (el detalle completo se registra en %LOG%)

"%PYEXE%" -m unittest discover -s tests -v >> "%LOG%" 2>&1
set "RESULT=%errorlevel%"

rem Resumen en consola
for /f "tokens=*" %%l in ('type "%LOG%" ^| findstr /c:"Ran " ') do echo %%l
if %RESULT% equ 0 (
    for /f "tokens=*" %%l in ('type "%LOG%" ^| findstr /b /c:"OK" ') do echo %%l
) else (
    echo ------------------------------------------------------------
    echo Fallos detectados:
    type "%LOG%" | findstr /c:"FAIL:" /c:"ERROR:" /c:"FAILED"
)
echo.
if %RESULT% equ 0 (
    echo PRUEBAS: CORRECTAS
    echo Registro: %LOG%
) else (
    echo PRUEBAS: CON FALLOS - revise %LOG%
)
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN OK 02_PRUEBAS.bat
endlocal
exit /b %RESULT%

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
