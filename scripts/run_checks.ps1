# Скрипт для локального запуска всех проверок CI
Write-Host "Starting local CI checks..." -ForegroundColor Cyan

# Проверяем и устанавливаем зависимости
$tools = @("pre-commit", "ruff", "mypy", "bandit", "safety")
foreach ($tool in $tools) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "$tool not found. Installing..." -ForegroundColor Yellow
        pip install $tool
    }
}

# Инициализируем pre-commit если нужно
if (-not (Test-Path .git/hooks/pre-commit)) {
    Write-Host "Initializing pre-commit..." -ForegroundColor Yellow
    pre-commit install
}

$ErrorActionPreference = "Continue"
$error_occurred = $false

Write-Host "`n[1/5] Running pre-commit checks..." -ForegroundColor Green
pre-commit run ruff --all-files
pre-commit run ruff-format --all-files
pre-commit run mypy --all-files
pre-commit run bandit --all-files
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pre-commit checks failed" -ForegroundColor Red
    $error_occurred = $true
}

Write-Host "`n[2/5] Running Ruff linter..." -ForegroundColor Green
ruff check .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ruff checks failed" -ForegroundColor Red
    $error_occurred = $true
}

Write-Host "`n[3/5] Running MyPy type checker..." -ForegroundColor Green
mypy . --ignore-missing-imports
if ($LASTEXITCODE -ne 0) {
    Write-Host "Type checks failed" -ForegroundColor Red
    $error_occurred = $true
}

Write-Host "`n[4/5] Running Bandit security checks..." -ForegroundColor Green
bandit --ini .bandit.ini -r
if ($LASTEXITCODE -ne 0) {
    # Для уровня MEDIUM и выше - это ошибка
    Write-Host "Security checks failed (medium or high severity issues found)" -ForegroundColor Red
    $error_occurred = $true
} elseif ($LASTEXITCODE -eq 0) {
    Write-Host "Security checks passed (no medium/high severity issues)" -ForegroundColor Green
}

Write-Host "`n[5/5] Checking dependencies for vulnerabilities..." -ForegroundColor Green
safety check
if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: Vulnerabilities found in dependencies" -ForegroundColor Yellow
}

if ($error_occurred) {
    Write-Host "`nSome checks failed! Please fix the issues above." -ForegroundColor Red
    exit 1
} else {
    Write-Host "`nAll checks passed successfully!" -ForegroundColor Green
}