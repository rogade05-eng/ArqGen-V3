@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Instalacion de dependencias

rem =====================================================================
rem  ARQ GEN - 01_INSTALAR_DEPENDENCIAS.bat
rem  Ejecutar UNA sola vez (requiere internet solo aqui).
rem  Crea el entorno virtual .venv e instala:
rem    - requirements.txt        (ezdxf, openpyxl  -> ejecucion)
rem    - requirements-build.txt  (pyinstaller      -> compilacion)
rem  Despues de esto, ARQ GEN funciona 100%% offline.
rem  Registro completo en logs\setup\.
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 01_INSTALAR_DEPENDENCIAS.bat scripts v1.6.4

if not exist logs\setup mkdir logs\setup
for /f "usebackq" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%i"
if not defined STAMP set "STAMP=%RANDOM%%RANDOM%"
set "LOG=logs\setup\install_%STAMP%.log"

>>"%LOG%" echo ============================================================
>>"%LOG%" echo [%DATE% %TIME%] ARQ GEN - Instalacion de dependencias
>>"%LOG%" echo ============================================================

rem --- Resolver interprete base -------------------------------------------
if exist "%ROOT%\.venv\Scripts\python.exe" goto have_venv
if defined ARQ_PY_EXE (
    set "BASEPY=%ARQ_PY_EXE%"
    goto have_base
)
if exist "%ROOT%\config\python_home.txt" (
    set /p BASEPY=<"%ROOT%\config\python_home.txt"
    goto have_base
)
call :resolve_fallback
set "BASEPY=%PYEXE%"
if not defined BASEPY (
    >>"%LOG%" echo [ERROR] Sin interprete base - falta .venv, no hay config y no hay Python en PATH.
    echo ERROR: no se encontro Python. Instale Python 3.13 marcando
    echo "Add python.exe to PATH" y vuelva a ejecutar este script.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

:have_base
if exist "%BASEPY%" goto base_ok
echo [AVISO] El interprete guardado no existe: %BASEPY%
>>"%LOG%" echo [AVISO] Interprete base guardado inexistente: %BASEPY%
call :resolve_fallback
set "BASEPY=%PYEXE%"
if not defined BASEPY (
    >>"%LOG%" echo [ERROR] Sin interprete base disponible tras reintentar deteccion.
    echo ERROR: no se encontro Python. Instale Python 3.13 marcando
    echo "Add python.exe to PATH" y vuelva a ejecutar este script.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
:base_ok
echo Interprete base: %BASEPY%
>>"%LOG%" echo [INFO] Interprete base: %BASEPY%

rem --- Crear entorno virtual ----------------------------------------------
echo Creando entorno virtual .venv ...
>>"%LOG%" echo [INFO] Creando .venv
"%BASEPY%" -m venv .venv >> "%LOG%" 2>&1
if errorlevel 1 (
    >>"%LOG%" echo [ERROR] No se pudo crear el entorno virtual.
    echo ERROR creando el entorno virtual. Detalle:
    type "%LOG%"
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
goto have_py

:have_venv
>>"%LOG%" echo [INFO] .venv ya existe: se reutiliza
echo Entorno virtual .venv ya existe: se reutiliza.

:have_py
set "PYEXE=%ROOT%\.venv\Scripts\python.exe"

rem --- Actualizar pip ------------------------------------------------------
echo Actualizando pip ...
>>"%LOG%" echo [INFO] Upgrade de pip
"%PYEXE%" -m pip install --upgrade pip >> "%LOG%" 2>&1
if errorlevel 1 >>"%LOG%" echo [AVISO] No se pudo actualizar pip - no es bloqueante

rem --- Instalar dependencias ----------------------------------------------
echo Instalando dependencias de ejecucion y compilacion ...
echo (puede tardar varios minutos; el detalle va al log)
>>"%LOG%" echo [INFO] pip install -r requirements.txt -r requirements-build.txt
"%PYEXE%" -m pip install --prefer-binary -r requirements.txt -r requirements-build.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    >>"%LOG%" echo [ERROR] Fallo la instalacion de dependencias.
    echo ============================================================
    echo ERROR instalando dependencias. Detalle:
    type "%LOG%"
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

rem --- Verificar importaciones --------------------------------------------
echo Verificando importaciones ...
>>"%LOG%" echo [INFO] Verificacion de importaciones
"%PYEXE%" -c "import ezdxf, openpyxl; print('ezdxf', ezdxf.__version__, '| openpyxl', openpyxl.__version__)" >> "%LOG%" 2>&1
if errorlevel 1 (
    >>"%LOG%" echo [ERROR] Las dependencias no se importan correctamente.
    echo ERROR de importacion. Detalle:
    type "%LOG%"
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

rem --- Congelar versiones instaladas ---------------------------------------
"%PYEXE%" -m pip freeze > logs\setup\pip_freeze_%STAMP%.txt 2>> "%LOG%"
>>"%LOG%" echo [INFO] Versiones congeladas en logs\setup\pip_freeze_%STAMP%.txt

set "LIBS=desconocidas"
for /f "usebackq tokens=*" %%v in (`"%PYEXE%" -c "import ezdxf,openpyxl;print('ezdxf '+ezdxf.__version__+' / openpyxl '+openpyxl.__version__)" 2^>nul`) do set "LIBS=%%v"

echo.
echo ============================================================
echo  DEPENDENCIAS INSTALADAS CORRECTAMENTE
echo  Librerias : %LIBS%
echo  Registro  : %LOG%
echo  A partir de ahora ARQ GEN funciona 100%% offline.
echo ============================================================
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN OK 01_INSTALAR_DEPENDENCIAS.bat
endlocal
exit /b 0

rem ==================== SUBRUTINAS ====================

:resolve_fallback
set "PYEXE="
for %%C in ("py -3.13" "python3.13" "py" "python" "python3") do (
    if not defined PYEXE call :try_candidate %%C
)
goto :eof

:try_candidate
rem %1 = candidato entre comillas (puede contener espacios, p.ej. "py -3.13")
set "PYEXE="
for /f "usebackq tokens=*" %%i in (`%~1 -c "import sys;print(sys.executable)" 2^>nul`) do set "PYEXE=%%i"
if not defined PYEXE goto :eof
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 set "PYEXE="
goto :eof
