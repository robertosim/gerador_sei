@echo off
title Gerador SEI
cd /d "%~dp0"

echo ============================================================
echo  Gerador SEI - verificacao de dependencias
echo ============================================================
python check.py
if errorlevel 1 (
    echo.
    echo A verificacao falhou. Corrija as mensagens acima e tente de novo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Encerrando servidor antigo (porta 5000), se houver
echo ============================================================
powershell -NoProfile -Command "$p = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id $p.OwningProcess -Force; Start-Sleep -Seconds 1; 'Servidor antigo encerrado.' } else { 'Nenhum servidor antigo na porta 5000.' }"

echo.
echo ============================================================
echo  Iniciando o aplicativo
echo ============================================================
python app.py
