$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        throw '请先运行 .\setup.ps1'
    }
    & .\.venv\Scripts\python.exe scripts/check_environment.py
    if ($LASTEXITCODE -ne 0) { throw '环境不可用，请运行 .\setup.ps1 -Python <Python解释器路径>' }
    & .\.venv\Scripts\python.exe scripts/launch_app.py
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed. See the error above.' }
} finally {
    Pop-Location
}
