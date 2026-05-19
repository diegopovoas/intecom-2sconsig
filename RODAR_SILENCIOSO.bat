@echo off
cd /d "C:\Users\diego.povoas\Desktop\2S_BI"
set LOG=C:\Users\diego.povoas\Desktop\2S_BI\log_execucao.txt
set NO_BROWSER=1

echo [%DATE% %TIME%] Iniciando atualizacao... > "%LOG%"

python "C:\Users\diego.povoas\Desktop\2S_BI\atualizar_via_db.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] AVISO: falha ao atualizar via banco. >> "%LOG%"
) else (
    echo [%DATE% %TIME%] Banco atualizado com sucesso. >> "%LOG%"
)

python "C:\Users\diego.povoas\Desktop\2S_BI\processar_2s.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] ERRO: falha ao gerar painel. >> "%LOG%"
    exit /b 1
) else (
    echo [%DATE% %TIME%] Painel gerado com sucesso. >> "%LOG%"
)

cd /d "C:\Users\diego.povoas\Desktop\2S_BI"
git add painel_bi_2s.html >> "%LOG%" 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Painel atualizado automaticamente" >> "%LOG%" 2>&1
)
git push origin master >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] AVISO: falha ao publicar no GitHub. >> "%LOG%"
) else (
    echo [%DATE% %TIME%] Publicado no GitHub com sucesso. >> "%LOG%"
)

echo [%DATE% %TIME%] Concluido. >> "%LOG%"
