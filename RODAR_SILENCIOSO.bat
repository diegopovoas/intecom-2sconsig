@echo off
cd /d "%~dp0"
set LOG=%~dp0log_execucao.txt
set NO_BROWSER=1

echo [%DATE% %TIME%] Iniciando atualizacao... > "%LOG%"

python "%~dp0atualizar_via_db.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] AVISO: falha ao atualizar via banco. >> "%LOG%"
) else (
    echo [%DATE% %TIME%] Banco atualizado com sucesso. >> "%LOG%"
)

python "%~dp0processar_2s.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] ERRO: falha ao gerar painel. >> "%LOG%"
    exit /b 1
) else (
    echo [%DATE% %TIME%] Painel gerado com sucesso. >> "%LOG%"
)

python "%~dp0publicar_supabase.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] AVISO: falha ao publicar no Supabase. >> "%LOG%"
) else (
    echo [%DATE% %TIME%] Publicado no Supabase com sucesso. >> "%LOG%"
)

echo [%DATE% %TIME%] Concluido. >> "%LOG%"
