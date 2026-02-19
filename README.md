# Telegram Mini App - Подработки в Минске

Веб-приложение для поиска подработок в Минске через Telegram Mini App.

## Структура проекта

```
├── backend/          # FastAPI бэкенд
│   ├── main.py      # Главный файл приложения
│   ├── database.py  # Настройка БД
│   ├── models.py    # Модели SQLAlchemy
│   ├── schemas.py   # Pydantic схемы
│   └── routes.py    # API роуты
├── frontend/         # Фронтенд (HTML/JS/CSS)
│   ├── index.html   # Главная страница
│   └── app.js       # JavaScript логика
├── requirements.txt # Python зависимости
└── README.md        # Этот файл
```

## Установка и настройка

### 1. Установка PostgreSQL

Следуйте инструкциям в файле `INSTALL_POSTGRESQL.md`

### 2. Установка Python зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка переменных окружения

Создайте файл `.env` в корне проекта (скопируйте из `env.example.txt`):

**Для SQLite (рекомендуется, не требует установки):**
```env
DB_TYPE=sqlite
DATABASE_URL=sqlite:///./minsk_jobs.db
TELEGRAM_BOT_TOKEN=ваш_токен_бота
YANDEX_MAPS_API_KEY=ваш_ключ_яндекс_карт
SECRET_KEY=любая_случайная_строка
```

**Для PostgreSQL:**
```env
DB_TYPE=postgresql
DATABASE_URL=postgresql://postgres:ваш_пароль@localhost:5432/minsk_jobs_db
TELEGRAM_BOT_TOKEN=ваш_токен_бота
YANDEX_MAPS_API_KEY=ваш_ключ_яндекс_карт
SECRET_KEY=любая_случайная_строка
```

### 4. Создание базы данных

База данных создастся автоматически при первом запуске сервера.

**Для SQLite:** Файл `minsk_jobs.db` создастся автоматически в корне проекта.

**Для PostgreSQL:** Если нужно создать вручную:
```bash
python -c "from backend.database import init_db; init_db()"
```

### 5. Получение Telegram Bot Token

Следуйте инструкциям в файле `SETUP_TELEGRAM_BOT.md`

### 6. Получение Яндекс.Карты API ключа

Следуйте инструкциям в файле `SETUP_YANDEX_MAPS.md`

### 7. Настройка API ключа в frontend

Откройте `frontend/index.html` и замените `YOUR_YANDEX_API_KEY` на ваш реальный ключ:

```html
<script src="https://api-maps.yandex.ru/2.1/?apikey=ВАШ_КЛЮЧ&lang=ru_RU" type="text/javascript"></script>
```

## Запуск приложения

### Запуск бэкенда

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Или из корня проекта:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Сервер будет доступен по адресу: `http://localhost:8000`

### Проверка работы

Откройте в браузере: `http://localhost:8000/api/health`

Должен вернуться: `{"status": "ok"}`

## Подключение к Telegram Mini App

После запуска сервера:

1. Убедитесь, что сервер доступен из интернета (используйте ngrok для локальной разработки)
2. В настройках бота через @BotFather добавьте Web App:
   ```
   /newapp
   Выберите вашего бота
   Название: Подработки Минск
   Описание: Поиск подработок в Минске
   URL: https://ваш_домен.com
   ```

## API Endpoints

- `POST /api/auth/telegram` - Авторизация через Telegram
- `GET /api/listings` - Получить все объявления
- `POST /api/listings` - Создать объявление
- `GET /api/listings/my` - Мои объявления
- `GET /api/listings/{id}` - Получить объявление по ID
- `DELETE /api/listings/{id}` - Удалить объявление

## Разработка

### Локальная разработка без Telegram

Для тестирования без Telegram можно временно отключить проверку авторизации в `backend/routes.py` (не рекомендуется для продакшена).

### Отладка

Логи FastAPI выводятся в консоль. Для более детальной отладки используйте:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Технологии

- **Backend**: Python 3.x, FastAPI, SQLAlchemy, PostgreSQL
- **Frontend**: HTML, JavaScript, CSS, Telegram WebApp SDK, Яндекс.Карты API
- **База данных**: PostgreSQL

