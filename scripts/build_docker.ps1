# Скрипт для локальной сборки и проверки Docker-образа
Write-Host "Starting local Docker build..." -ForegroundColor Cyan

# Проверяем наличие Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is not installed!" -ForegroundColor Red
    exit 1
}

# Собираем образ
$IMAGE_NAME = "random_coffee_bot:local"
Write-Host "`nBuilding Docker image..." -ForegroundColor Green
docker build -t $IMAGE_NAME .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker build failed" -ForegroundColor Red
    exit 1
}

# Проверяем образ на уязвимости (если установлен trivy)
if (Get-Command trivy -ErrorAction SilentlyContinue) {
    Write-Host "`nScanning image for vulnerabilities..." -ForegroundColor Green
    trivy image $IMAGE_NAME
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: Vulnerabilities found in the image" -ForegroundColor Yellow
    }
} else {
    Write-Host "`nWarning: Trivy is not installed. Skipping image scan." -ForegroundColor Yellow
    Write-Host "To install Trivy: https://aquasecurity.github.io/trivy/latest/getting-started/installation/" -ForegroundColor Gray
}

Write-Host "`nBuild and scan completed!" -ForegroundColor Green