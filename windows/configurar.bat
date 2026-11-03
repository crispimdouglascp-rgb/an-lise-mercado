@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
set "PROJ=%CD%"
set "DADOS=%USERPROFILE%\RVLocal-dados"
set RVLOCAL_HOME=
echo.
echo ===== RV Local: configuração (não precisa de administrador) =====
echo.
where python >nul 2>nul || (echo [ERRO] Python não encontrado. Instale em python.org marcando "Add python.exe to PATH". & pause & exit /b 1)

echo [1/6] Instalando/atualizando o programa...
python -m pip install -q -e ".[painel]" || (echo [ERRO] Falha no pip. Veja a mensagem acima. & pause & exit /b 1)

echo [2/6] Apagando dados de teste (base DEMO)...
if exist "%PROJ%\demo\DADOS-DEMO.md" (rmdir /s /q "%PROJ%\demo" & echo       base demo apagada.) else (echo       nenhuma base demo encontrada.)
if exist "%PROJ%\painel-estatico" rmdir /s /q "%PROJ%\painel-estatico"

echo [3/6] Criando a sua pasta de dados em %DADOS% ...
if exist "%DADOS%\data\livros" (
  echo       já existe: mantida, nada foi apagado.
  >"%PROJ%\.rvlocal-home" echo %DADOS%
) else (
  python -m rvlocal iniciar --destino "%DADOS%" || (echo [ERRO] Não foi possível criar a pasta. & pause & exit /b 1)
)

echo [4/6] Testando as fontes de preço (Yahoo, brapi, BCB)...
python -m rvlocal testar-fontes
if errorlevel 1 echo       AVISO: alguma fonte falhou. A rede da empresa pode bloquear; sem preço, a coleta grava lacuna (nunca inventa).

echo [5/6] Agendando as rotinas automáticas...
call "%~dp0instalar-rotina.bat"

echo [6/6] Criando atalho "RV Local" na área de trabalho...
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESK=%%D"
(
  echo @echo off
  echo call "%PROJ%\windows\abrir-painel.bat"
) > "%DESK%\RV Local.bat"
echo       atalho criado em %DESK%\RV Local.bat

echo.
python -m rvlocal onde
echo.
echo Pronto. Dê dois cliques em "RV Local" na área de trabalho para abrir o painel.
echo A cola com os comandos está em %DADOS%\COLA.md
pause
