param(
    [int]$DebounceSeconds = 45,
    [int]$PollSeconds = 3
)

# Следит за изменениями в рабочем каталоге и автоматически коммитит их
# после периода тишины. Работает с любым агентом или редактором.
# Проверка идёт через git status, поэтому не зависит от событий файловой системы.

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = cmd /c "git rev-parse --show-toplevel 2>nul"
if (-not $root) {
    Write-Host "watch_commit: git-репозиторий не найден." -ForegroundColor Red
    exit 1
}
Set-Location $root

Write-Host "watch_commit: слежу за $root" -ForegroundColor Cyan
Write-Host "watch_commit: автокоммит после $DebounceSeconds с без изменений. Ctrl+C - остановить." -ForegroundColor Cyan

$lastStatus = (git status --porcelain) -join "`n"
$lastChange = Get-Date

while ($true) {
    Start-Sleep -Seconds $PollSeconds

    $status = (git status --porcelain) -join "`n"
    if ($status -ne $lastStatus) {
        $lastStatus = $status
        $lastChange = Get-Date
        continue
    }

    if ($lastStatus -and ((Get-Date) - $lastChange).TotalSeconds -ge $DebounceSeconds) {
        & (Join-Path $root "scripts\auto_commit.ps1")
        $lastStatus = (git status --porcelain) -join "`n"
        $lastChange = Get-Date
    }
}
