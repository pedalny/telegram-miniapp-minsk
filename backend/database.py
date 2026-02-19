from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Определяем тип базы данных из переменной окружения
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE == "postgresql":
    # Использование PostgreSQL (если доступен)
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("❌ DATABASE_URL не установлен! Установите переменную окружения DATABASE_URL для PostgreSQL.")
    
    # Проверяем, что это действительно PostgreSQL URL
    if not DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgres://"):
        raise ValueError(f"❌ Неверный формат DATABASE_URL для PostgreSQL: {DATABASE_URL[:50]}...")
    
    print(f"📊 Используется PostgreSQL")
    print(f"📊 DATABASE_URL: {DATABASE_URL[:50]}..." if len(DATABASE_URL) > 50 else f"📊 DATABASE_URL: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)
else:
    # Использование SQLite (по умолчанию, не требует установки)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./minsk_jobs.db")
    print(f"📊 Используется SQLite")
    print(f"⚠️  ВНИМАНИЕ: SQLite на Render теряет данные при перезапуске!")
    print(f"📊 DATABASE_URL: {DATABASE_URL}")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}  # Нужно для SQLite с FastAPI
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Создание всех таблиц в базе данных"""
    try:
        Base.metadata.create_all(bind=engine)
        print(f"✅ База данных инициализирована: {DB_TYPE.upper()}")
        print(f"📊 DATABASE_URL: {DATABASE_URL[:50]}..." if len(DATABASE_URL) > 50 else f"📊 DATABASE_URL: {DATABASE_URL}")
        
        # Проверяем подключение
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Подключение к базе данных успешно!")
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        raise

