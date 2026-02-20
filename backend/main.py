from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os

# Импортируем модули как часть пакета backend
from .routes import router
from .json_storage import _ensure_data_file, get_stats

app = FastAPI(title="Minsk Jobs Telegram Mini App")

# CORS для разработки (в продакшене можно ограничить)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роуты API
app.include_router(router)

# Путь к фронтенду
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")

# Отдаём статику по /static
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.on_event("startup")
async def startup_event():
    """Инициализация JSON хранилища при запуске"""
    import os
    from .json_storage import DATA_PATH
    
    print("=" * 50)
    print("🚀 Запуск приложения...")
    print(f"📁 Хранилище данных: JSON файл")
    print(f"📁 Путь к файлу: {DATA_PATH}")
    print("=" * 50)
    
    try:
        # Создаем файл данных если его нет
        _ensure_data_file()
        
        # Показываем статистику
        stats = get_stats()
        print(f"👥 Пользователей в хранилище: {stats['users_count']}")
        print(f"📋 Всего объявлений: {stats['listings_count']}")
        print(f"✅ Активных объявлений: {stats['active_listings_count']}")
        print("✅ Приложение готово к работе")
        print("=" * 50)
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА при инициализации хранилища: {e}")
        import traceback
        traceback.print_exc()
        raise


@app.get("/api/health")
async def health_check():
    """Проверка работоспособности API"""
    return {"status": "ok"}


@app.get("/")
async def index():
    """
    Отдаём основной HTML (Telegram Mini App) по корню /
    """
    index_file = os.path.join(frontend_path, "index.html")
    return FileResponse(index_file)


@app.get("/board.html")
async def board():
    """
    Отдаём страницу доски объявлений
    """
    board_file = os.path.join(frontend_path, "board.html")
    return FileResponse(board_file)

