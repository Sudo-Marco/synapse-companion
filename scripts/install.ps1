$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand -or $pythonCommand.Source -match '\\Microsoft\\WindowsApps\\python(?:3)?\.exe$') {
    throw 'Python 3.10+ was not found. Install Python and enable its PATH option, then rerun this script.'
}
& $pythonCommand.Source --version
if ($LASTEXITCODE -ne 0) { throw 'The selected Python command could not start.' }
& $pythonCommand.Source -m venv (Join-Path $project '.venv')
$python = Join-Path $project '.venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
$spec = $project + '[dev,windows]'
& $python -m pip install -e $spec
