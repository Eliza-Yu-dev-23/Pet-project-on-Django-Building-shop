# Запуск проекта «СтройБаза».
# Скрипт сам поднимает Docker Desktop, если движок не запущен,
# ждёт готовности и выполняет docker compose up -d --build.

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Test-DockerEngine {
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

if (-not (Test-DockerEngine)) {
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) {
        Write-Host "Docker Desktop не запущен — запускаю..." -ForegroundColor Yellow
        Start-Process $desktop
        Write-Host "Ожидание Docker Engine (до 3 минут)..." -ForegroundColor Yellow
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 3
            if (Test-DockerEngine) { break }
        }
    }
}

if (-not (Test-DockerEngine)) {
    Write-Host "Docker Engine недоступен." -ForegroundColor Red
    Write-Host "Установите и запустите Docker Desktop, затем повторите запуск." -ForegroundColor Red
    exit 1
}

Write-Host "Сборка и запуск контейнеров..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Ожидание ответа приложения..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/login/" -TimeoutSec 5
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}

docker compose ps

if (-not $ready) {
    Write-Host "Контейнеры запущены, но приложение не отвечает." -ForegroundColor Red
    Write-Host "Посмотрите логи: docker compose logs web" -ForegroundColor Red
    exit 1
}

Write-Host "Готово: http://localhost:8000" -ForegroundColor Green
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (Test-Path $chrome) {
    Start-Process $chrome "http://localhost:8000"
} else {
    Start-Process "http://localhost:8000"
}
