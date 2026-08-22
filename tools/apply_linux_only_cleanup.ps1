$ErrorActionPreference = 'Stop'

$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo '.git'))) {
    throw 'Run this script from the root of your existing SNTalkBot Git repository.'
}

$staleFiles = @(
    'bot/gui.py',
    'requirements-gui.txt',
    'setup.bat',
    'run_bot.bat'
)

foreach ($relative in $staleFiles) {
    $path = Join-Path $repo $relative
    if (Test-Path $path) {
        Remove-Item -Force $path
        Write-Host "Removed: $relative"
    }
}

Write-Host ''
Write-Host 'Linux/Docker-only cleanup complete.'
Write-Host 'Review changes with: git status'
Write-Host 'Then commit with: git add -A; git commit -m "Remove GUI and Windows runtime files"; git push'
