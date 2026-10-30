@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Demo end-to-end

rem =====================================================================
rem  ARQ GEN - 06_DEMO.bat
rem  Genera el proyecto de demostracion completo y exporta a output\:
rem    - demo.arqgen  (proyecto: 4 locales, 7 muros, 4 puertas, 3 ventanas,
rem                    4 redes de instalaciones: electrica, agua fria,
rem                    desague y extraccion)
rem    - demo.dxf     (plano por niveles, capas ARQ-*)
rem    - demo.json    (instantanea completa)
rem    - demo.xlsx    (cantidades + presupuesto)
rem    - presupuesto.csv / cantidades.csv
rem  Registro en logs\app\.
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 06_DEMO.bat scripts v1.6.4

if not exist output mkdir output
if not exist logs\app mkdir logs\app
for /f "usebackq" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%i"
if not defined STAMP set "STAMP=%RANDOM%%RANDOM%"
set "LOG=logs\app\demo_%STAMP%.log"

call :resolve_py
if not defined PYEXE (
    echo ERROR: no se encontro interprete de Python. Instale Python 3.13
    echo marcando "Add python.exe to PATH", y vuelva a ejecutar este script.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

>>"%LOG%" echo ============================================================
>>"%LOG%" echo [%DATE% %TIME%] ARQ GEN - Demo end-to-end
>>"%LOG%" echo ============================================================

echo [1/6] Creando proyecto demo ...
"%PYEXE%" main.py --log-dir logs demo --out output\demo.arqgen >> "%LOG%" 2>&1
if errorlevel 1 goto error

echo [2/6] Validando proyecto ...
"%PYEXE%" main.py --log-dir logs validate output\demo.arqgen >> "%LOG%" 2>&1
if errorlevel 1 goto error

echo [3/6] Exportando plano DXF y planilla XLSX ...
"%PYEXE%" main.py --log-dir logs export output\demo.arqgen --format dxf --out output\demo.dxf >> "%LOG%" 2>&1
if errorlevel 1 goto error
"%PYEXE%" main.py --log-dir logs export output\demo.arqgen --format xlsx --out output\demo.xlsx >> "%LOG%" 2>&1
if errorlevel 1 goto error

echo [4/6] Exportando instantanea JSON ...
"%PYEXE%" main.py --log-dir logs export output\demo.arqgen --format json --out output\demo.json >> "%LOG%" 2>&1
if errorlevel 1 goto error

echo [5/6] Exportando CSV de presupuesto y cantidades ...
"%PYEXE%" main.py --log-dir logs export output\demo.arqgen --format csv --table budget --out output\presupuesto.csv >> "%LOG%" 2>&1
if errorlevel 1 goto error
"%PYEXE%" main.py --log-dir logs export output\demo.arqgen --format csv --table quantities --out output\cantidades.csv >> "%LOG%" 2>&1
if errorlevel 1 goto error

echo [6/6] Resumen del proyecto ...
"%PYEXE%" main.py --log-dir logs project info output\demo.arqgen >> "%LOG%" 2>&1
if errorlevel 1 goto error
"%PYEXE%" main.py --log-dir logs project info output\demo.arqgen

echo.
echo ============================================================
echo  DEMO COMPLETADA - archivos generados en output\
echo  Registro: %LOG%
echo ============================================================
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN OK 06_DEMO.bat
endlocal
exit /b 0

:error
echo.
echo ERROR: la demo fallo en uno de los pasos. Detalle:
type "%LOG%"
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN ERROR 06_DEMO.bat
exit /b 1

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
