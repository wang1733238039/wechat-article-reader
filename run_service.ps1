# WeChat Download API - 后台启动脚本
# 双击运行，自动检测环境，在后台启动服务

$ErrorActionPreference = "Stop"
$BASE_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV_DIR = Join-Path $BASE_DIR "venv"
$ENV_FILE = Join-Path $BASE_DIR ".env"

function Find-Python {
    $paths = @(
        (Join-Path $VENV_DIR "Scripts\python.exe"),
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python310\python.exe",
        "C:\Program Files\Python39\python.exe",
        "python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$PY = Find-Python

if (-not $PY) {
    $msg = @"
未检测到 Python 环境！

请先安装 Python 3.8+，然后重新运行本脚本。
下载地址: https://www.python.org/downloads/
"@
    [System.Windows.Forms.MessageBox]::Show($msg, "WeChat Download API", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    Start-Process "https://www.python.org/downloads/"
    exit 1
}

# 虚拟环境
if (-not (Test-Path $VENV_DIR)) {
    & $PY -m venv $VENV_DIR
}
$PY_VENV = Join-Path $VENV_DIR "Scripts\python.exe"
if (-not (Test-Path $PY_VENV)) { $PY_VENV = $PY }

# 依赖
Write-Host "Checking dependencies..."
& $PY_VENV -m pip install --upgrade pip --quiet 2>$null
& $PY_VENV -m pip install -r (Join-Path $BASE_DIR "requirements.txt") --quiet 2>$null

# .env
if (-not (Test-Path $ENV_FILE)) {
    $ex = Join-Path $BASE_DIR "env.example"
    if (Test-Path $ex) { Copy-Item $ex $ENV_FILE }
}

# 启动
$LOG = Join-Path $BASE_DIR "service.log"
$ERR = Join-Path $BASE_DIR "service.err"

Write-Host "Starting WeChat Download API..."

# 先杀掉旧进程
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*wechat-download-api*" -or $_.Path -like "*venv*"
} | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep 1

$proc = Start-Process -FilePath $PY_VENV `
    -ArgumentList "app.py" `
    -WorkingDirectory $BASE_DIR `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LOG `
    -RedirectStandardError $ERR

Start-Sleep 3

if ($proc.HasExited) {
    Write-Host "ERROR: Process exited with code $($proc.ExitCode)"
    if (Test-Path $ERR) { Get-Content $ERR | Select-Object -First 5 }
} else {
    Write-Host "OK: Service started (PID: $($proc.Id))"
    Write-Host "Admin:   http://localhost:5001/static/admin.html"
    Write-Host "Login:   http://localhost:5001/static/login.html"
    Write-Host "Docs:    http://localhost:5001/api/docs"
}
