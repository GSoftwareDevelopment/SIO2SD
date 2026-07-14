@echo off
rem ---------------------------------------------------------------
rem Uruchamia serwer emulacji SIO2SD dla Altirry.
rem Karta SD = katalog sd\ obok tego pliku (tworzony, gdy go brak).
rem Dodatkowe opcje mozna dopisac przy wywolaniu, np.:
rem     sio2sd_server.bat -v
rem     sio2sd_server.bat --mount 2=GRA.ATR
rem ---------------------------------------------------------------
setlocal
set "SD=%~dp0sd"
if not exist "%SD%" mkdir "%SD%"
python "%~dp0altirra\sio2sd_server.py" -v "%SD%" %*
if errorlevel 1 pause
endlocal
