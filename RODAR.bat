@echo off
cd /d "%~dp0"
title 2S Consig - Atualizando e Gerando Painel BI...
color 0A
echo.
echo  ================================================
echo   2S CONSIG - ATUALIZAR + GERAR PAINEL BI
echo  ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ERRO: Python nao encontrado!
    echo  Instale em: https://www.python.org/downloads/
    echo  Na instalacao, marque "Add Python to PATH"
    pause
    exit /b
)

set NO_BROWSER=1
echo  Verificando dependencias...
pip install pandas openpyxl pymysql pyarrow requests --quiet --disable-pip-version-check 2>nul
echo.

echo  [Etapa 1/2] Atualizando Producao via banco MySQL...
echo.
python atualizar_via_db.py
if errorlevel 1 (
    echo.
    echo  AVISO: falha ao atualizar via banco. Vou gerar painel com a base atual.
    echo.
    timeout /t 3 >nul
)
echo.

echo  [Etapa 2/3] Processando dados e gerando painel...
echo.
python processar_2s.py
if errorlevel 1 (
    echo.
    echo  ERRO: falha ao gerar painel. Verifique os dados.
    pause
    exit /b
)
echo.

echo  [Etapa 3/3] Publicando painel no GitHub...
echo.
cd /d "%~dp0"
git add painel_bi_2s.html index.html
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Painel atualizado automaticamente"
) else (
    echo  Painel sem alteracoes, pulando commit.
)
git push origin master
if errorlevel 1 (
    echo  AVISO: nao foi possivel publicar no GitHub.
    echo  Verifique sua conexao ou autenticacao do Git.
) else (
    echo  Painel publicado com sucesso!
    echo.
    echo  Acesse em:
    echo  https://diegopovoas.github.io/intecom-2sconsig/
)
echo.
pause
