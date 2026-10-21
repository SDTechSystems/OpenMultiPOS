@echo off
rem Local Windows launcher. Uses the default Linux account configured in Ubuntu.
wsl.exe -d Ubuntu -u root -- systemctl start mariadb redis-server
if errorlevel 1 goto failure
wsl.exe -d Ubuntu -- systemctl --user start openmultipos-web openmultipos-worker openmultipos-backup.timer
if errorlevel 1 goto failure
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; Start-Process -FilePath 'wsl.exe' -ArgumentList '-d Ubuntu --cd ~ --exec .local/share/openmultipos/bench/env/bin/python -m open_multi_pos.keepalive' -WindowStyle Hidden"
if errorlevel 1 goto failure
for /L %%i in (1,1,10) do (
  wsl.exe -d Ubuntu --cd ~ --exec .local/share/openmultipos/bench/env/bin/python -m open_multi_pos.keepalive --check
  if not errorlevel 1 goto ready
  timeout /t 1 /nobreak >nul
)
goto failure
:ready
start "" "http://omp.localhost:8000/omp"
exit /b 0
:failure
echo No se pudo iniciar OpenMultiPOS. Revisa WSL y los servicios siguiendo el manual.
pause
exit /b 1
