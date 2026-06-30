# Start standalone Qdrant server for local development.
#
# Docker Desktop is currently unavailable on this machine. Qdrant runs
# as a standalone Windows binary on the L drive.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/start_qdrant.ps1
#
# Binary:   L:\AssistGen\.tools\qdrant\bin\qdrant.exe
# Config:   L:\AssistGen\.tools\qdrant\config.yaml
# Data:     L:\AssistGen\.data\qdrant
# URL:      http://127.0.0.1:6333

param(
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "L:\AssistGen"
$QdrantBin   = "$ProjectRoot\.tools\qdrant\bin\qdrant.exe"
$QdrantConf  = "$ProjectRoot\.tools\qdrant\config.yaml"
$QdrantData  = "$ProjectRoot\.data\qdrant"
$QdrantUrl   = "http://127.0.0.1:6333/collections"

# ── Check if Qdrant is already running ──────────────────────────────
try {
    $response = Invoke-WebRequest -Uri $QdrantUrl -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "[INFO] Qdrant already running at http://127.0.0.1:6333"
        exit 0
    }
} catch {
    # Not responding — proceed to start.
}

# ── Verify binary and data directory ────────────────────────────────
if (-not (Test-Path $QdrantBin)) {
    Write-Host "[ERROR] Qdrant binary not found: $QdrantBin"
    Write-Host "        Download from https://github.com/qdrant/qdrant/releases"
    exit 1
}

if (-not (Test-Path $QdrantData)) {
    New-Item -ItemType Directory -Path $QdrantData -Force | Out-Null
    Write-Host "[INFO] Created data directory: $QdrantData"
}

# ── Start Qdrant ────────────────────────────────────────────────────
Write-Host "[INFO] Starting Qdrant..."
Write-Host "       Binary: $QdrantBin"
Write-Host "       Config: $QdrantConf"
Write-Host "       Data:   $QdrantData"

$process = Start-Process `
    -FilePath $QdrantBin `
    -ArgumentList "--config-path", $QdrantConf `
    -PassThru `
    -NoNewWindow

# ── Wait for Qdrant to respond ──────────────────────────────────────
$elapsed = 0
$interval = 2
while ($elapsed -lt $TimeoutSeconds) {
    Start-Sleep -Seconds $interval
    $elapsed += $interval
    try {
        $response = Invoke-WebRequest -Uri $QdrantUrl -TimeoutSec 3 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Host "[OK] Qdrant is ready (PID=$($process.Id), port=6333, waited ${elapsed}s)"
            exit 0
        }
    } catch {
        Write-Host "       ... waiting (${elapsed}s)"
    }
}

Write-Host "[WARN] Qdrant process started but did not respond within ${TimeoutSeconds}s"
Write-Host "       Process PID: $($process.Id)"
Write-Host "       Check logs or try http://127.0.0.1:6333/collections manually."
exit 1
