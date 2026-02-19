from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os

# Импортируем модули как часть пакета backend
from .routes import router
from .database import init_db

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
    """Инициализация базы данных при запуске"""
    init_db()
    print("База данных инициализирована")


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

