@echo off
cd /d "%~dp0"
echo.
echo  Criando tarefa agendada: 2S_BI_Atualizar (a cada 10 minutos)
echo.

schtasks /delete /tn "2S_BI_Atualizar" /f >nul 2>&1

schtasks /create ^
  /tn "2S_BI_Atualizar" ^
  /tr "\"%~dp0ATUALIZAR_SILENCIOSO.bat\"" ^
  /sc minute ^
  /mo 10 ^
  /st 00:00 ^
  /ru "%USERNAME%" ^
  /f

if errorlevel 1 (
    echo  ERRO ao criar tarefa agendada.
    pause
    exit /b 1
)

echo.
echo  Tarefa criada com sucesso!
echo  O painel sera atualizado a cada 10 minutos automaticamente.
echo.
echo  Para verificar: Agendador de Tarefas do Windows ^> 2S_BI_Atualizar
echo  Para remover:   schtasks /delete /tn "2S_BI_Atualizar" /f
echo.
pause
