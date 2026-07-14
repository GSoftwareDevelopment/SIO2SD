@echo off
rem ---------------------------------------------------------------
rem Buduje okienkowy plik EXE dla graficznego panelu SIO2SD.
rem Wymaga PyInstaller: py -3 -m pip install pyinstaller
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

py -3 -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Brak PyInstaller.
    echo Zainstaluj go poleceniem:
    echo py -3 -m pip install pyinstaller
    exit /b 1
)

py -3 -m PyInstaller --clean --noconfirm sio2sd_gui.spec
if errorlevel 1 (
    echo.
    echo Budowanie EXE nie powiodlo sie.
    exit /b 1
)

echo.
echo Gotowe: dist\SIO2SD-GUI.exe
endlocal
