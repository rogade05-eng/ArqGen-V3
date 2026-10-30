@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Ejecutar version compilada

rem =====================================================================
rem  ARQ GEN - 05_EJECUTAR_COMPILADO.bat
rem  Ejecuta el ejecutable generado por 03_COMPILAR.bat.
rem  Ejemplos:
rem     05_EJECUTAR_COMPILADO.bat project info output\demo.arqgen
rem     05_EJECUTAR_COMPILADO.bat selftest
rem     05_EJECUTAR_COMPILADO.bat gui
rem  Sin argumentos muestra la ayuda (la ventana no se cierra sola).
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 05_EJECUTAR_COMPILADO.bat scripts v1.6.4

if not exist "dist\ARQ_GEN\ARQ_GEN.exe" (
    echo ERROR: no existe dist\ARQ_GEN\ARQ_GEN.exe
    echo Ejecute primero 03_COMPILAR.bat
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

if "%~1"=="" (
    echo Modo de uso: 05_EJECUTAR_COMPILADO.bat [comando] [argumentos]
    echo Ejemplos: selftest, gui, project info output\demo.arqgen
    echo.
    echo INTERFAZ GRAFICA: ejecute 09_GUI_COMPILADO.bat, o haga doble
    echo clic en dist\ARQ_GEN\ARQ_GEN.exe - abre la ventana directamente.
    echo.
    echo ------------------------------------------------------------
    dist\ARQ_GEN\ARQ_GEN.exe help
    echo ------------------------------------------------------------
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 0
)

dist\ARQ_GEN\ARQ_GEN.exe %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo ARQ_GEN.exe termino con codigo %RC%.
    echo.
    if not defined ARQ_NOPAUSE pause
)
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN 05_EJECUTAR_COMPILADO.bat codigo=%RC%
exit /b %RC%
