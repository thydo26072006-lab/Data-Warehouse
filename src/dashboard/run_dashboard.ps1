$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pythonPath = Join-Path $projectRoot '.runtime/forecast-venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Chua co moi truong Python. Xem src/dashboard/README.md de cai dat.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -X utf8 src/warehouse/setup_local_postgres.py
    if ($LASTEXITCODE -ne 0) { throw 'Khong khoi dong duoc PostgreSQL.' }
    & $pythonPath -m streamlit run src/dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
} finally {
    Pop-Location
}
