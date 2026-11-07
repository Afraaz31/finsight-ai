# FinSight AI - start the whole demo with one command.
# Usage (from the project folder):   powershell -ExecutionPolicy Bypass -File run_demo.ps1
# Opens two windows (API and UI) and then your browser. Close those windows to stop.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Host "Virtual environment not found at $python" -ForegroundColor Red; exit 1 }

Write-Host "Starting FinSight API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$python' -m uvicorn backend.main:app --port 8000"

# Wait until the API answers /health (loading the embedding model takes a few seconds)
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 2 | Out-Null; $ready = $true; break }
    catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { Write-Host "API did not start - check the API window for errors." -ForegroundColor Red; exit 1 }

Write-Host "Starting FinSight UI on http://localhost:8501 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$python' -m streamlit run frontend/app.py --server.headless true"
Start-Sleep -Seconds 6
Start-Process "http://localhost:8501"
Start-Process "http://127.0.0.1:8000/docs"
Write-Host "FinSight AI is running. UI: http://localhost:8501   API docs: http://127.0.0.1:8000/docs" -ForegroundColor Green
