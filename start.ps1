# Warden: one-command local start (Windows PowerShell).
#   .\start.ps1            start everything (first run installs dependencies and builds the graph)
#   .\start.ps1 -Reset     same, then restore the clean demo state (golden graph, no approvals)
#   .\start.ps1 -Test      run the backend tests and exit
param([switch]$Reset, [switch]$Test)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function PortBusy($p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }

Step "Checking tools"
foreach ($tool in "docker", "python", "npm", "git") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed or not on PATH" }
}
docker info *> $null
if (-not $?) { throw "Docker is not running. Start Docker Desktop and try again." }

if (-not (Test-Path (Join-Path $root ".env"))) {
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
    Write-Host "Created .env from .env.example. Add LLM_API_KEY (and GitHub settings) to use the agent and PRs." -ForegroundColor Yellow
}

Step "Starting FalkorDB (graph :6380, Browser :3000) and Postgres (:5433)"
docker compose -f (Join-Path $root "docker-compose.yml") up -d falkordb postgres | Out-Null

Step "Backend dependencies"
if (-not (Test-Path $py)) { python -m venv (Join-Path $backend ".venv") }
& $py -m pip install -q -r (Join-Path $backend "requirements.txt")

Step "Frontend dependencies"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) { npm --prefix $frontend install --silent }

Push-Location $backend
try {
    if ($Test) { Step "Running backend tests"; & $py -m pytest -q tests; exit $LASTEXITCODE }

    Step "Building the graph if it's empty (first run takes about a minute)"
    for ($i = 0; $i -lt 15; $i++) {
        & $py -c "from warden.graph.client import db; db().list_graphs()" 2>$null
        if ($?) { break }
        Start-Sleep -Seconds 1
    }
    & $py -m warden.ingest.bootstrap

    if ($Reset) {
        Step "Resetting to the clean demo state"
        & $py -c "from warden import sync; print(sync.reset())"
    }
} finally { Pop-Location }

Step "Starting the API (:8000) and the website (:5173) in new windows"
if (PortBusy 8000) { Write-Host "Port 8000 is already in use: an API is probably running already. Skipping." -ForegroundColor Yellow }
else { Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m uvicorn warden.api.app:app --port 8000" }
if (PortBusy 5173) { Write-Host "Port 5173 is already in use: the website is probably running already. Skipping." -ForegroundColor Yellow }
else { Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev" }

Step "Waiting for the API"
for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 }
}
Start-Process "http://localhost:5173"
Write-Host "`nWarden is up:  http://localhost:5173   (API http://localhost:8000/docs, FalkorDB Browser http://localhost:3000)" -ForegroundColor Green
