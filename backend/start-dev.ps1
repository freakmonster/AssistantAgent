# 一键启动后端开发环境：ARQ worker + uvicorn（FastAPI）
# 用法：在任意位置执行  powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
#       或直接在 backend 目录执行  .\start-dev.ps1
# 说明：会打开两个新窗口，分别运行 ARQ worker 与 uvicorn；停止时关闭对应窗口即可。

$ErrorActionPreference = "Stop"

# 定位脚本所在目录（backend），无论从何处调用都能正确切到工作目录
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境 Python：$python`n请先在 backend 目录创建 .venv 并安装依赖。"
    exit 1
}

Write-Host "== 后端开发环境 ==" -ForegroundColor Cyan
Write-Host "  工作目录 : $root"
Write-Host "  API      : http://127.0.0.1:8016"
Write-Host "  Worker   : arq app.tasks.worker.WorkerSettings"
Write-Host ""

# 启动 ARQ worker（新窗口，消费视频等异步任务）
Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "arq", "app.tasks.worker.WorkerSettings") `
    -WorkingDirectory $root

# 启动 uvicorn（新窗口，--reload 热重载）
Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8016", "--reload") `
    -WorkingDirectory $root

Write-Host "已启动两个窗口：ARQ worker 与 uvicorn。" -ForegroundColor Green
Write-Host "停止时直接关闭对应窗口即可。"
