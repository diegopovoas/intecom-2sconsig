@echo off
title 2S BI - Servidor Web
cd /d "%~dp0"

echo.
echo  =====================================================
echo    2S CONSIG - Iniciando Servidor do Painel BI
echo  =====================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ERRO: Python nao encontrado.
    pause
    exit /b 1
)

pip install flask -q

echo  Servidor iniciando na porta 8080...
echo  Acesse: http://localhost:8080
echo.
python servidor.py
pause
