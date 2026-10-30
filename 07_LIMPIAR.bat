@echo off
chcp 65001 >nul
setlocal
title ARQ GEN - Limpieza de artefactos

rem =====================================================================
rem  ARQ GEN - 07_LIMPIAR.bat
rem  Elimina artefactos de compilacion y caches. NO toca proyectos
rem  (.arqgen), backups, ni logs.
rem =====================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

rem Latido de arranque: prueba temprana de que este script llego a ejecutarse
if not exist logs mkdir logs
>>"logs\bat_boot.log" echo [%DATE% %TIME%] INICIO 07_LIMPIAR.bat scripts v1.6.4

echo Esta operacion elimina: build\ dist\ __pycache__ y archivos .pyc
echo NO elimina proyectos .arqgen, ni la carpeta backups\, ni logs\
echo.
choice /c SN /m "Continuar (S=si, N=no)"
if errorlevel 2 exit /b 0

echo Limpiando ...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc >nul 2>&1

echo.
echo Limpieza terminada.
echo.
if not defined ARQ_NOPAUSE pause
>>"logs\bat_boot.log" echo [%DATE% %TIME%] FIN OK 07_LIMPIAR.bat
endlocal
exit /b 0
