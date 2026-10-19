$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
Set-Location $root

Write-Host "Starting the database and Redis (your data lives in the Docker volume 'backend_piano_pgdata')..."
docker compose up -d
for ($i = 0; $i -lt 60; $i++) {
  docker compose exec -T db pg_isready -U piano -d piano *> $null
  if ($LASTEXITCODE -eq 0) { break }
  Start-Sleep -Seconds 1
}

$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Write-Host "First run: creating the Python environment..."
  python -m venv (Join-Path $backend ".venv")
}
& $python -m pip install --quiet -r (Join-Path $backend "requirements.txt")

$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
  Copy-Item (Join-Path $backend ".env.example") $envFile
}
Push-Location $backend
& $python -m alembic upgrade head
& $python -m app.seed
Pop-Location

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$python' -m uvicorn app.main:app --reload --port 8000"

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
  Push-Location $frontend
  npm install
  Pop-Location
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev"

Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
