# Install ffmpeg on Windows via winget.
# Usage: powershell -ExecutionPolicy Bypass -File install_ffmpeg.ps1

$ErrorActionPreference = "Stop"

Write-Host "==> Checking if ffmpeg is already installed..."
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
    Write-Host "ffmpeg already installed: $($ffmpeg.Source)"
    exit 0
}

Write-Host "==> ffmpeg not found. Trying to install Gyan.FFmpeg via winget..."
$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-Error "winget not found. Please install ffmpeg manually from https://www.gyan.dev/ffmpeg/builds/ and add it to PATH."
    exit 1
}

winget install --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements

# Refresh PATH in the current session so the newly installed ffmpeg is immediately available.
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = $machinePath + ";" + $userPath

Write-Host "==> Verifying ffmpeg installation..."
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
    Write-Host "ffmpeg installed successfully: $($ffmpeg.Source)"
    & ffmpeg -version | Select-Object -First 1
} else {
    Write-Warning "winget ran but ffmpeg is not visible in the current session. Please open a new terminal and re-run."
    exit 1
}
