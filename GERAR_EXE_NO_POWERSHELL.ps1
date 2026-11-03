# Compila o aplicativo em um EXE usando PowerShell
$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$App = Join-Path $AppDir "configurador_mikrotik.py"

if (-not (Test-Path $App)) {
    throw "Não encontrei configurador_mikrotik.py na pasta do script."
}

$PythonCmd = Get-Command py -ErrorAction SilentlyContinue
if ($PythonCmd) {
    $Python = "py"
    $PythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
    $PythonArgs = @()
} else {
    throw "Python não encontrado. Instale Python para Windows e marque Add Python to PATH."
}

Write-Host "Atualizando pip e instalando PyInstaller..." -ForegroundColor Cyan
& $Python @PythonArgs -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar pip." }

& $Python @PythonArgs -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar PyInstaller." }

Write-Host "Gerando o executável..." -ForegroundColor Cyan
Push-Location $AppDir
try {
    & $Python @PythonArgs -m PyInstaller --noconfirm --clean --onefile --windowed --name Configurador_MikroTik $App
    if ($LASTEXITCODE -ne 0) { throw "A compilação falhou." }
} finally {
    Pop-Location
}

$Exe = Join-Path $AppDir "dist\Configurador_MikroTik.exe"
if (Test-Path $Exe) {
    Write-Host "EXE criado com sucesso: $Exe" -ForegroundColor Green
} else {
    throw "A compilação terminou, mas o EXE não foi encontrado."
}
