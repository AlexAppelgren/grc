# Poetry wrapper for the backend, PowerShell edition of run.sh (playbook 2.1). Usage:
#
#   .\run.ps1 run python manage.py test apps --settings=config.test_settings
#
# Unsets VIRTUAL_ENV so Poetry 2 uses the project's own environment rather than whatever
# the calling shell had activated, then runs `poetry <args>` from the backend directory.
$ErrorActionPreference = "Stop"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Set-Location $PSScriptRoot
& poetry @args
exit $LASTEXITCODE
