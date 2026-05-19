@echo off
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

echo  [Etapa 2/2] Processando dados e gerando painel...
echo.
python processar_2s.py
