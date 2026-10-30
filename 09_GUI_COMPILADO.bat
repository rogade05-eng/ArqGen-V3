@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Interfaz grafica compilada

rem =====================================================================
rem  ARQ GEN - 09_GUI_COMPILADO.bat
rem  Abre la INTERFAZ GRAFICA (FASE 90, spec 90-93) desde el ejecutable
rem  compilado dist\ARQ_GEN\ARQ_GEN.exe. NO necesita Python instalado:
rem  todo va dentro del ejecutable.
rem  Argumentos opcionales: [archivo.arqgen] [--demo] [--width N --height N]
rem  Sin argumentos se abre el proyecto de demostracion.
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 09_GUI_COMPILADO.bat scripts v1.6.4

if not exist "dist\ARQ_GEN\ARQ_GEN.exe" (
    echo ERROR: no existe dist\ARQ_GEN\ARQ_GEN.exe
    echo Ejecute primero 03_COMPILAR.bat para generar el ejecutable.
    echo.
    if not defined ARQ_NOPAUSE pause
    exit /b 1
)

echo Abriendo la interfaz grafica de ARQ GEN...
echo  - Se abre la ventana con el proyecto de demostracion.
echo  - La consola queda ocupada hasta que cierre la ventana.
echo.
>>"logs\bat_boot.log" echo [%DATE% %TIME%] GUI compilada lanzada desde 09
dist\ARQ_GEN\ARQ_GEN.exe gui %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo ARQ_GEN.exe gui termino con codigo %RC%.
    echo Revise logs\app\errors.log si fue un error inesperado.
    echo.
    if not defined ARQ_NOPAUSE pause
)
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN 09_GUI_COMPILADO.bat codigo=%RC%
exit /b %RC%
