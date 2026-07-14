@echo off
rem ---------------------------------------------------------------
rem Uruchamia graficzny panel serwera SIO2SD dla Altirry.
rem ---------------------------------------------------------------
setlocal
python "%~dp0altirra\sio2sd_gui.py" %*
if errorlevel 1 pause
endlocal
