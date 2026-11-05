# Starts the FitMeal bot and starts it again if it ever stops. Press Ctrl+C in this window to stop for good.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File C:\path\to\Fitmeal\scripts\start-bot.ps1
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
& "$project\.venv\Scripts\Activate.ps1"
while ($true) {
    python -m bot.main
    Write-Host "The bot stopped. Starting again in 10 seconds (Ctrl+C to quit)..."
    Start-Sleep -Seconds 10
}
