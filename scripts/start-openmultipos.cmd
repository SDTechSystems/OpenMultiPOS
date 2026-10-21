@echo off
rem Local Windows launcher. Uses the default Linux account configured in Ubuntu.
wsl.exe -d Ubuntu -u root -- systemctl start mariadb redis-server
if errorlevel 1 goto failure
wsl.exe -d Ubuntu -- systemctl --user start openmultipos-web openmultipos-worker openmultipos-backup.timer
if errorlevel 1 goto failure
start "" "http://omp.localhost:8000/omp"
exit /b 0
:failure
echo No se pudo iniciar OpenMultiPOS. Revisa WSL y los servicios siguiendo el manual.
pause
exit /b 1
