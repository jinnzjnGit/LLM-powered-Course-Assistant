param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12+ required'"
    if ($LASTEXITCODE -ne 0) { throw "请安装Python 3.12，或用-Python指定解释器路径。" }
    # 升级解释器绑定，保留已有包；不删除用户文件。
    & $Python -m venv --upgrade .venv
    if ($LASTEXITCODE -ne 0) { throw "虚拟环境创建失败。" }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "依赖安装失败，请检查网络与软件源。" }
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    & .\.venv\Scripts\python.exe scripts/check_environment.py
    if ($LASTEXITCODE -ne 0) { throw "环境检查未通过。" }
    Write-Host '安装完成。填写.env后运行 .\start.ps1'
} finally {
    Pop-Location
}
