@echo off
title Libera GeradorSEI.exe - Windows Defender
cd /d "%~dp0"

rem ------------------------------------------------------------------
rem Libera a execucao do GeradorSEI.exe (Windows Defender / ASR).
rem
rem   liberar-executavel.bat            adiciona a pasta as exclusoes
rem   liberar-executavel.bat /regra     + desativa a regra de ASR que
rem                                      bloqueia executavel novo
rem
rem Rode com um clique: a janela se auto-eleva para administrador.
rem ------------------------------------------------------------------

rem Requisita administrador (reabre a si mesmo elevado)
net session >nul 2>&1
if errorlevel 1 (
    echo Pedindo permissao de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================================
echo  Liberando a execucao de GeradorSEI.exe
echo  Pasta: %CD%
echo ============================================================
echo.

if exist "%CD%\GeradorSEI.exe" goto pasta_ok
if exist "%CD%\dist\GeradorSEI.exe" (
    echo [INFO] GeradorSEI.exe encontrado em "dist": a exclusao desta pasta
    echo        ja cobre as subpastas, entao esta tudo certo.
    echo.
    goto pasta_ok
)
echo [AVISO] GeradorSEI.exe nao foi encontrado nesta pasta nem em "dist".
echo         Copie este .bat para a pasta do .exe (ou o .exe para ca)
echo         e rode de novo.
echo.
:pasta_ok

echo [1/2] Adicionando a pasta as exclusoes do Defender...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Add-MpPreference -ExclusionPath '%CD%'; Write-Host '      OK: pasta excluida do scan e das regras de ASR.' } catch { Write-Host ('      FALHA: ' + $_) }"

echo.
if /i "%~1"=="/regra" (
    echo [2/2] Desativando a regra de ASR que bloqueia executavel novo...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Add-MpPreference -AttackSurfaceReductionRules_Ids 'BE9BA2D9-53EA-4CDC-84E5-9B1EEEE46550' -AttackSurfaceReductionRules_Actions Disabled; Write-Host '      OK: regra de ASR desativada nesta maquina.' } catch { Write-Host ('      FALHA: ' + $_) }"
) else (
    echo [2/2] Regra de ASR mantida ^(protecao do Windows^).
    echo       Se ainda bloquear, rode: liberar-executavel.bat /regra
)

echo.
echo Verificando...
powershell -NoProfile -ExecutionPolicy Bypass -Command "if ((Get-MpPreference).ExclusionPath -contains '%CD%') { Write-Host '      Pasta confirmada na lista de exclusoes.' } else { Write-Host '      ATENCAO: pasta nao consta na lista (protecao contra adulteracao ligada ou politica de empresa).' }"

echo.
echo ============================================================
echo  Concluido. Se o Windows mostrar "Windows protegeu seu
echo  computador" ao abrir o .exe, clique em:
echo      Mais informacoes ^> Executar assim mesmo
echo  (isso e o SmartScreen, nao o Defender - nao volta a ocorrer
echo  depois de executado uma vez)
echo ============================================================
echo.
echo Para desfazer:
echo   Remove-MpPreference -ExclusionPath "%CD%"
echo   (com /regra) Add-MpPreference -AttackSurfaceReductionRules_Ids 'BE9BA2D9-53EA-4CDC-84E5-9B1EEEE46550' -AttackSurfaceReductionRules_Actions Enabled
echo.
pause
