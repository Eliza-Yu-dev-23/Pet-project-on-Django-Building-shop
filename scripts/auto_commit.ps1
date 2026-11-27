param(
    [string]$Message = "",
    [switch]$Push
)

# Автокоммит изменений. Вызывается вручную, из Stop-hook Claude Code
# или из watch_commit.ps1. Если изменений нет, ничего не делает.

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = cmd /c "git rev-parse --show-toplevel 2>nul"
if (-not $root) {
    Write-Host "auto_commit: git-репозиторий не найден." -ForegroundColor Red
    exit 1
}
Set-Location $root

$gitDir = git rev-parse --git-dir
$busyMarkers = @("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
$busy = $busyMarkers | Where-Object { Test-Path (Join-Path $gitDir $_) }
if ($busy -or (Test-Path (Join-Path $gitDir "rebase-merge")) -or (Test-Path (Join-Path $gitDir "rebase-apply"))) {
    Write-Host "auto_commit: идёт merge/rebase - пропускаю." -ForegroundColor Yellow
    exit 0
}

$changes = git status --porcelain
if (-not $changes) {
    exit 0
}

if (-not $Message) {
    $Message = "chore: автосохранение изменений ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))"
}

git add -A
if ($LASTEXITCODE -ne 0) {
    Write-Host "auto_commit: не удалось добавить файлы в индекс." -ForegroundColor Red
    exit 1
}

git commit -m $Message
if ($LASTEXITCODE -ne 0) {
    Write-Host "auto_commit: коммит не создан." -ForegroundColor Red
    exit 1
}

if ($Push) {
    git push
    if ($LASTEXITCODE -ne 0) {
        Write-Host "auto_commit: коммит создан, но push не удался." -ForegroundColor Red
        exit 1
    }
}

Write-Host "auto_commit: $Message" -ForegroundColor Green
exit 0
