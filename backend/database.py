from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Определяем тип базы данных из переменной окружения
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE == "postgresql":
    # Использование PostgreSQL (если доступен)
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/minsk_jobs_db")
    engine = create_engine(DATABASE_URL)
else:
    # Использование SQLite (по умолчанию, не требует установки)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./minsk_jobs.db")
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
    Base.metadata.create_all(bind=engine)
    print(f"База данных инициализирована: {DB_TYPE.upper()}")

