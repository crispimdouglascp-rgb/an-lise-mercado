@echo off
chcp 65001 >nul
rem Abre o painel. Se já estiver rodando, só abre o navegador.
set RVLOCAL_HOME=
netstat -ano | findstr /r /c:":8765 .*LISTENING" >nul
if %errorlevel%==0 (
  start "" http://127.0.0.1:8765
  exit /b 0
)
set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"
start "RV Local - painel" /min "%PYW%" -m rvlocal painel
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8765
