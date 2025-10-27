# Random Coffee Bot

## Локальный запуск проверок CI

### Предварительные требования

1. Python 3.12+
2. Git
3. Docker (для проверки сборки образа)
4. [Trivy](https://aquasecurity.github.io/trivy/latest/getting-started/installation/) (опционально, для проверки образа на уязвимости)

### Установка инструментов

```powershell
# Установка зависимостей для разработки
pip install -r requirements.txt

# Установка pre-commit хуков
pre-commit install
```

### Запуск проверок

1. Запуск всех проверок кода:
```powershell
.\scripts\run_checks.ps1
```

Это выполнит:
- Линтинг (ruff)
- Проверку типов (mypy)
- Проверку безопасности (bandit)
- Проверку уязвимостей в зависимостях (safety)
- Pre-commit хуки

2. Проверка сборки Docker-образа:
```powershell
.\scripts\build_docker.ps1
```

Это выполнит:
- Сборку Docker-образа
- Сканирование образа на уязвимости (если установлен Trivy)

### Отдельные проверки

Можно запускать проверки по отдельности:

```powershell
# Линтинг
ruff check .

# Проверка типов
mypy . --ignore-missing-imports

# Проверка безопасности
bandit -r . -ll -ii

# Проверка зависимостей
safety check

# Pre-commit хуки
pre-commit run --all-files
```

### Автоматические исправления

```powershell
# Автоисправление проблем линтера
ruff check . --fix

# Форматирование кода
ruff format .
```

### CI/CD Pipeline

Полный CI/CD pipeline в GitHub Actions включает:
1. Проверки кода (как описано выше)
2. Сборку Docker-образа
3. Публикацию образа в GitHub Container Registry

Локальные проверки помогают убедиться, что код пройдет CI до отправки в репозиторий.