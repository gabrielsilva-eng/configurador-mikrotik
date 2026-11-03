# Executa a interface do Configurador MikroTik pelo PowerShell
$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$App = Join-Path $AppDir "configurador_mikrotik.py"

if (-not (Test-Path $App)) {
    Write-Host "Não encontrei configurador_mikrotik.py na pasta do script." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) {
    & py -3 $App
    exit $LASTEXITCODE
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) {
    & python $App
    exit $LASTEXITCODE
}

Write-Host "Python não foi encontrado." -ForegroundColor Yellow
Write-Host "Instale o Python para Windows e marque 'Add Python to PATH'."
Write-Host "Depois feche e abra o PowerShell novamente."
Read-Host "Pressione Enter para sair"
exit 1
