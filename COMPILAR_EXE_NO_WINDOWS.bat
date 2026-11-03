@echo off
chcp 65001 >nul
title Compilar Configurador MikroTik
echo ==========================================
echo  Compilador do Configurador MikroTik
echo ==========================================
echo.
echo Este processo exige Python e PyInstaller no computador de compilacao.
echo O usuario final NAO precisara de Python depois que o EXE for criado.
echo.
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo Falha ao instalar PyInstaller. Verifique a conexao e o Python.
  pause
  exit /b 1
)
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Configurador_MikroTik configurador_mikrotik.py
if errorlevel 1 (
  echo Falha na compilacao.
  pause
  exit /b 1
)
echo.
echo EXE criado em: dist\Configurador_MikroTik.exe
pause
