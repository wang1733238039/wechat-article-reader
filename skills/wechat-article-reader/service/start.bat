@echo off
chcp 65001 > nul

:: 强制在持久cmd窗口中运行（双击效果）
if "%1"=="" (
    cmd /k "%~f0" run
    exit /b
)

title WeChat Download API

echo.
echo ========================================
echo   WeChat Download API  一键启动
echo ========================================
echo.

:: Configuration
set PYTHON_VERSION=3.12
set PYTHON_MSI_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
set PYTHON_MSI_BACKUP=https://npm.taobao.org/mirrors/python/3.12.8/python-3.12.8-amd64.exe
set VENV_NAME=venv
set PYTHON_EXE=

:: ================================================
:: Step 1: 查找或安装 Python
:: ================================================
echo [94m[1/5] 检查 Python 环境...[0m

python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXE=python
    for /f "tokens=2" %%i in ('python --version') do set VER=%%i
    echo [92m  发现 Python %VER%[0m
    goto :check_pip
)

:: 未找到，尝试常见路径
if exist "C:\Program Files\Python312\python.exe" (
    set PYTHON_EXE=C:\Program Files\Python312\python.exe
    echo [92m  发现 Python 3.12[0m
    goto :check_pip
)
if exist "C:\Program Files\Python311\python.exe" (
    set PYTHON_EXE=C:\Program Files\Python311\python.exe
    echo [92m  发现 Python 3.11[0m
    goto :check_pip
)
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_EXE=C:\Program Files\Python310\python.exe
    echo [92m  发现 Python 3.10[0m
    goto :check_pip
)

:: 未安装，提示下载
echo.
echo [91m  未检测到 Python 环境！[0m
echo.
echo   本工具需要 Python %PYTHON_VERSION%+ 才能运行。
echo   即将自动打开下载页面...
echo.
pause

start "" "https://www.python.org/downloads/"
echo.
echo [93m  请下载并安装 Python %PYTHON_VERSION%+[0m
echo [93m  安装时请勾选: "Add Python to PATH"[0m
echo.
echo [93m  安装完成后，重新双击运行本脚本。[0m
echo.
pause
exit /b 1

:: ================================================
:: Step 2: 检查 pip
:: ================================================
:check_pip
echo.
echo [94m[2/5] 检查 pip...[0m

if defined PYTHON_EXE (
    %PYTHON_EXE% -m pip --version >nul 2>&1
) else (
    python -m pip --version >nul 2>&1
)

if not errorlevel 1 (
    echo [92m  pip 正常[0m
    goto :venv
)

echo [91m  pip 不可用，尝试安装...[0m
if defined PYTHON_EXE (
    %PYTHON_EXE% -m ensurepip --default-pip >nul 2>&1
) else (
    python -m ensurepip --default-pip >nul 2>&1
)
if errorlevel 1 (
    echo [91m  pip 安装失败，请手动安装 pip 后重试[0m
    pause
    exit /b 1
)
echo [92m  pip 安装完成[0m

:: ================================================
:: Step 3: 创建虚拟环境
:: ================================================
:venv
echo.
echo [94m[3/5] 配置虚拟环境...[0m

if exist "%VENV_NAME%" (
    echo [93m  虚拟环境已存在，跳过创建[0m
) else (
    if defined PYTHON_EXE (
        %PYTHON_EXE% -m venv %VENV_NAME%
    ) else (
        python -m venv %VENV_NAME%
    )
    if not errorlevel 1 (
        echo [92m  虚拟环境创建完成[0m
    ) else (
        echo [93m  虚拟环境创建失败，使用系统 Python[0m
        set "VENV_NAME="
    )
)

:: ================================================
:: Step 4: 安装依赖
:: ================================================
echo.
echo [94m[4/5] 安装依赖包...[0m

set "PY=python"
if exist "%VENV_NAME%\Scripts\python.exe" (
    set "PY=%VENV_NAME%\Scripts\python.exe"
    echo [92m  使用虚拟环境 Python[0m
)

%PY% -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [93m  pip 升级失败，继续安装依赖...[0m
)

%PY% -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo [93m  安装出现警告，重新安装（显示详情）...[0m
    %PY% -m pip install -r requirements.txt
) else (
    echo [92m  依赖安装完成[0m
)

:: ================================================
:: Step 5: 初始化 .env
:: ================================================
echo.
echo [94m[5/5] 检查配置文件...[0m

if not exist ".env" (
    if exist "env.example" (
        copy env.example .env >nul
        echo [92m  已创建 .env（首次使用请访问登录页面扫码）[0m
    )
) else (
    echo [92m  .env 已就绪[0m
)

:: ================================================
:: 启动服务
:: ================================================
echo.
echo ========================================
echo   [92m服务启动中...[0m
echo ========================================
echo.
echo   管理面板:  http://localhost:5001/static/admin.html
echo   扫码登录:  http://localhost:5001/static/login.html
echo   API 文档:  http://localhost:5001/api/docs
echo.
echo   首次使用: 打开扫码登录页面，用微信扫二维码
echo   停止服务:  按 Ctrl+C
echo.

%PY% app.py

echo.
echo 服务已停止
pause
