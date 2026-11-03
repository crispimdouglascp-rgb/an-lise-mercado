@echo off
chcp 65001 >nul
rem Roda uma rotina na hora, com a saída visível. Ex.: rodar-agora.bat fechar --todas
set RVLOCAL_HOME=
python -m rvlocal %*
pause
