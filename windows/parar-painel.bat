@echo off
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*rvlocal painel*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'painel encerrado (PID ' + $_.ProcessId + ')' }"
pause
