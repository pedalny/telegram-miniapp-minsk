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
    from .json_storage import DATA_PATH, DATA_DIR, DATA_FILE
    
    print("=" * 50)
    print("🚀 Запуск приложения...")
    print(f"📁 Хранилище данных: JSON файл")
    print(f"📁 Директория: {DATA_DIR}")
    print(f"📁 Файл: {DATA_FILE}")
    print(f"📁 Полный путь: {DATA_PATH}")
    print(f"📁 Директория существует: {os.path.exists(DATA_DIR)}")
    print(f"📁 Файл существует: {os.path.exists(DATA_PATH)}")
    print("=" * 50)
    
    try:
        # Проверяем состояние файла ДО инициализации
        file_existed_before = os.path.exists(DATA_PATH)
        if file_existed_before:
            file_size_before = os.path.getsize(DATA_PATH)
            print(f"📊 Файл данных существовал до инициализации: {file_size_before} байт")
        else:
            print(f"📊 Файл данных не существовал до инициализации")
        
        # Создаем файл данных если его нет (НЕ перезаписывает существующий!)
        _ensure_data_file()
        
        # Проверяем состояние файла ПОСЛЕ инициализации
        if os.path.exists(DATA_PATH):
            file_size_after = os.path.getsize(DATA_PATH)
            print(f"✅ Файл данных после инициализации: {DATA_PATH} (размер: {file_size_after} байт)")
            
            # Сравниваем размеры
            if file_existed_before and file_size_before != file_size_after:
                print(f"⚠️  ВНИМАНИЕ: размер файла изменился! Было: {file_size_before}, Стало: {file_size_after}")
            elif file_existed_before:
                print(f"✅ Размер файла не изменился - данные сохранены")
        else:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: файл данных не найден после инициализации!")
        
        # Показываем статистику
        stats = get_stats()
        print(f"👥 Пользователей в хранилище: {stats['users_count']}")
        print(f"📋 Всего объявлений: {stats['listings_count']}")
        print(f"✅ Активных объявлений: {stats['active_listings_count']}")
        
        # Предупреждение если данные потеряны
        if file_existed_before and stats['listings_count'] == 0:
            print(f"⚠️  ВНИМАНИЕ: Файл существовал, но объявлений нет! Возможно данные потеряны при деплое.")
            print(f"💡 РЕШЕНИЕ: Используй переменную окружения DATA_DIR для указания постоянного хранилища")
        
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

