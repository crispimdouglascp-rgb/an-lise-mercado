@echo off
chcp 65001 >nul
for %%T in ("RVLocal 1 Cobranca 0745" "RVLocal 2 Coleta manha 0820" "RVLocal 3 Flash 0940" "RVLocal 4 Vigilancia 10min" "RVLocal 5 Coleta fechamento" "RVLocal 6 Fechamento 1805" "RVLocal 7 Boletim diario" "RVLocal 8 Boletim semanal" "RVLocal 9 Boletim mensal") do schtasks /delete /f /tn %%T >nul 2>&1 && echo removida %%~T
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RVLocal-painel.bat" 2>nul
echo Rotinas removidas. Seus dados NÃO foram apagados.
pause
