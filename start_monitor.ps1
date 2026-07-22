$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3 was not found. Install Python and try again."
}

& python price_monitor.py --config config.json watch
