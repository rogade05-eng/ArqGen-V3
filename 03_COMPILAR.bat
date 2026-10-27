@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Compilacion (PyInstaller)

rem =====================================================================
rem  ARQ GEN - 03_COMPILAR.bat
rem  Pipeline completo de compilacion con registro de errores en las
rem  TRES etapas, cada una con su propio log:
rem    1. ANTES    : suite de pruebas        -> logs\tests\pre_build_*.log
rem    2. DURANTE  : empaquetado PyInstaller -> logs\build\build_*.log
rem    3. DESPUES  : selftest del ejecutable -> logs\tests\post_build_*.log
rem  Si cualquier etapa falla, el pipeline se detiene, muestra el log y
rem  la ventana permanece abierta (pause) para poder leer el error.
rem  Resultado: dist\ARQ_GEN\ARQ_GEN.exe (modo onedir)
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 03_COMPILAR.bat scripts v1.6.4

if not exist logs\build mkdir logs\build
if not exist logs\tests mkdir logs\tests
for /f "usebackq" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%i"
if not defined STAMP set "STAMP=%RANDOM%%RANDOM%"
set "LOG_PRE=logs\tests\pre_build_%STAMP%.log"
set "LOG_BUILD=logs\build\build_%STAMP%.log"
set "LOG_POST=logs\tests\post_build_%STAMP%.log"

call :resolve_py
if not defined PYEXE (
    echo ERROR: no se encontro interprete de Python. Instale Python 3.13
    echo marcando "Add python.exe to PATH", y vuelva a ejecutar este script.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

echo ============================================================
echo  ARQ GEN - PIPELINE DE COMPILACION (%STAMP%) - scripts v1.6.4
echo ============================================================

rem ================= ETAPA 1: PRUEBAS ANTES DE COMPILAR ====================
echo.
echo [1/3] PRUEBAS ANTES DE COMPILAR ...
>>"%LOG_PRE%" echo ============================================================
>>"%LOG_PRE%" echo [%DATE% %TIME%] PRUEBAS ANTES DE COMPILAR
>>"%LOG_PRE%" echo ============================================================
"%PYEXE%" -m unittest discover -s tests -v >> "%LOG_PRE%" 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: las pruebas ANTES de compilar fallaron. No se compila.
    echo Detalle en %LOG_PRE%
    echo ------------------------------------------------------------
    type "%LOG_PRE%" | findstr /c:"FAIL:" /c:"ERROR:" /c:"FAILED"
    echo ------------------------------------------------------------
    >>"%LOG_BUILD%" echo [ERROR] Etapa 1 - pruebas pre-compilacion fallida
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
for /f "tokens=*" %%l in ('type "%LOG_PRE%" ^| findstr /c:"Ran " ') do echo    %%l
echo    Resultado: OK  (log: %LOG_PRE%)

rem ================= ETAPA 2: COMPILACION ==================================
echo.
echo [2/3] COMPILANDO con PyInstaller (onedir) ...
>>"%LOG_BUILD%" echo ============================================================
>>"%LOG_BUILD%" echo [%DATE% %TIME%] COMPILACION PyInstaller
>>"%LOG_BUILD%" echo ============================================================
>>"%LOG_BUILD%" echo Interprete: %PYEXE%
>>"%LOG_BUILD%" echo [INFO] Limpiando compilaciones previas
>>"%LOG_BUILD%" echo [INFO] Se excluyen los bindings Qt PySide6 y PyQt5 - ARQ GEN usa Tkinter
if exist build rmdir /s /q build >> "%LOG_BUILD%" 2>&1
if exist dist rmdir /s /q dist >> "%LOG_BUILD%" 2>&1

rem Exclusion de TODOS los bindings Qt:
rem   ezdxf -> ezdxf.npshapes importa ezdxf.addons.xqt, que intenta
rem   "from PySide6 import ..." y "from PyQt5 import ..." con guardas
rem   try/except. Si ambos paquetes existen en el equipo, PyInstaller
rem   aborta con "attempt to collect multiple Qt bindings packages".
rem   ARQ GEN no usa Qt - su GUI es Tkinter - asi que se excluyen todos.
rem   El import de Qt en ezdxf es perezoso y nunca se ejecuta en ARQ GEN.
"%PYEXE%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --name ARQ_GEN ^
    --icon "resources\branding\logo.ico" ^
    --onedir ^
    --collect-submodules plugins.builtin ^
    --collect-submodules ui ^
    --add-data "resources;resources" ^
    --exclude-module PySide6 ^
    --exclude-module shiboken6 ^
    --exclude-module PySide2 ^
    --exclude-module shiboken2 ^
    --exclude-module PyQt5 ^
    --exclude-module PyQt6 ^
    main.py >> "%LOG_BUILD%" 2>&1

if errorlevel 1 (
    echo.
    echo ERROR: la COMPILACION fallo. Detalle en %LOG_BUILD%
    echo ------------------------------------------------------------
    echo Ultimas lineas del log de compilacion:
    powershell -NoProfile -Command "Get-Content '%LOG_BUILD%' -Tail 25"
    echo ------------------------------------------------------------
    >>"%LOG_BUILD%" echo [ERROR] Etapa 2 - compilacion fallida
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
if not exist "dist\ARQ_GEN\ARQ_GEN.exe" (
    >>"%LOG_BUILD%" echo [ERROR] PyInstaller termino pero no genero dist\ARQ_GEN\ARQ_GEN.exe
    echo ERROR: no se genero el ejecutable. Detalle en %LOG_BUILD%
    type "%LOG_BUILD%"
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
echo    Ejecutable generado: dist\ARQ_GEN\ARQ_GEN.exe
for %%F in (dist\ARQ_GEN\ARQ_GEN.exe) do echo    Tamano: %%~zF bytes
echo    Log de compilacion: %LOG_BUILD%

rem ================= ETAPA 3: PRUEBAS DESPUES DE COMPILAR ==================
echo.
echo [3/3] PRUEBAS DESPUES DE COMPILAR (selftest del ejecutable) ...
>>"%LOG_POST%" echo ============================================================
>>"%LOG_POST%" echo [%DATE% %TIME%] PRUEBAS DESPUES DE COMPILAR - selftest del ejecutable
>>"%LOG_POST%" echo ============================================================
dist\ARQ_GEN\ARQ_GEN.exe selftest >> "%LOG_POST%" 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: el selftest DEL EJECUTABLE fallo. Detalle en %LOG_POST%
    echo ------------------------------------------------------------
    type "%LOG_POST%"
    echo ------------------------------------------------------------
    >>"%LOG_BUILD%" echo [ERROR] Etapa 3 - selftest post-compilacion fallida
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)
type "%LOG_POST%"

echo.
echo ============================================================
echo  COMPILACION COMPLETADA CORRECTAMENTE
echo  Ejecutable : dist\ARQ_GEN\ARQ_GEN.exe
echo  Logs       : %LOG_PRE%
echo               %LOG_BUILD%
echo               %LOG_POST%
echo ============================================================
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN OK 03_COMPILAR.bat
endlocal
exit /b 0

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
