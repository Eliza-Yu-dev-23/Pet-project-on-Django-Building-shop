param(
    [int]$DebounceSeconds = 45
)

# Следит за каталогом проекта и автоматически коммитит изменения
# после периода тишины. Работает с любым агентом или редактором.

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = cmd /c "git rev-parse --show-toplevel 2>nul"
if (-not $root) {
    Write-Host "watch_commit: git-репозиторий не найден." -ForegroundColor Red
    exit 1
}
Set-Location $root

$global:lastChange = Get-Date
$global:pending = $false

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $root
$watcher.IncludeSubdirectories = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::LastWrite -bor [System.IO.NotifyFilters]::DirectoryName
$watcher.EnableRaisingEvents = $true

$action = {
    $path = $Event.SourceEventArgs.FullPath
    if ($path -match '[\\/]\.git[\\/]|[\\/]__pycache__[\\/]|[\\/]\.venv[\\/]|[\\/]node_modules[\\/]|[\\/]staticfiles[\\/]|\.pyc$') {
        return
    }
    $global:lastChange = Get-Date
    $global:pending = $true
}

$handlers = @()
foreach ($eventName in @("Changed", "Created", "Deleted", "Renamed")) {
    $handlers += Register-ObjectEvent -InputObject $watcher -EventName $eventName -Action $action
}

Write-Host "watch_commit: слежу за $root" -ForegroundColor Cyan
Write-Host "watch_commit: автокоммит после $DebounceSeconds с без изменений. Ctrl+C - остановить." -ForegroundColor Cyan

try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($global:pending -and ((Get-Date) - $global:lastChange).TotalSeconds -ge $DebounceSeconds) {
            $global:pending = $false
            & (Join-Path $root "scripts\auto_commit.ps1")
        }
    }
}
finally {
    foreach ($handler in $handlers) {
        Unregister-Event -SubscriptionId $handler.SubscriptionId -ErrorAction SilentlyContinue
    }
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
}
