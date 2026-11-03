@echo off
chcp 65001 >nul
rem Agenda as rotinas no Agendador de Tarefas do SEU usuário (sem administrador).
rem Rodam com o computador ligado e você logado. Sem janela (pythonw).
set "PYW="
for /f "delims=" %%P in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%P"
if not defined PYW for /f "delims=" %%P in ('where python') do if not defined PYW set "PYW=%%P"
set "DIAS=MON,TUE,WED,THU,FRI"
set OK=0
set FALHA=0
call :tarefa "RVLocal 1 Cobranca 0745"      "/sc weekly /d %DIAS% /st 07:45" "cobranca --todas"
call :tarefa "RVLocal 2 Coleta manha 0820"  "/sc weekly /d %DIAS% /st 08:20" "coletar --modo manha"
call :tarefa "RVLocal 3 Flash 0940"         "/sc weekly /d %DIAS% /st 09:40" "coletar --modo flash"
call :tarefa "RVLocal 4 Vigilancia 10min"   "/sc minute /mo 10 /st 09:45 /et 18:15" "vigiar"
call :tarefa "RVLocal 5 Coleta fechamento"  "/sc weekly /d %DIAS% /st 18:00" "coletar --modo fechamento"
call :tarefa "RVLocal 6 Fechamento 1805"    "/sc weekly /d %DIAS% /st 18:05" "fechar --todas"
call :tarefa "RVLocal 7 Boletim diario"     "/sc weekly /d %DIAS% /st 18:10" "boletim --tipo diario --todas"
call :tarefa "RVLocal 8 Boletim semanal"    "/sc weekly /d FRI /st 19:00" "boletim --tipo semanal --todas"
call :tarefa "RVLocal 9 Boletim mensal"     "/sc monthly /d 1 /st 08:10" "boletim --tipo mensal --data ontem --todas"

rem Painel ao ligar o computador: atalho na pasta Inicializar (não precisa de administrador)
set "INIT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
(
  echo @echo off
  echo start "RV Local - painel" /min "%PYW:python.exe=pythonw.exe%" -m rvlocal painel
) > "%INIT%\RVLocal-painel.bat"
echo       painel vai abrir sozinho quando você entrar no Windows.
echo       rotinas agendadas: %OK% ok, %FALHA% com erro.
exit /b 0

:tarefa
schtasks /create /f /tn %1 %~2 /tr "\"%PYW%\" -m rvlocal %~3" >nul 2>&1
if errorlevel 1 (set /a FALHA+=1 & echo       ERRO ao agendar %1) else (set /a OK+=1 & echo       agendada %~1)
exit /b 0
