from sqlalchemy import create_engine, text, inspect
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
        raise ValueError("DATABASE_URL не установлен. Установите переменную окружения DATABASE_URL для PostgreSQL.")
    
    # Проверяем, что это действительно PostgreSQL URL
    if not DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgres://"):
        raise ValueError(f"Неверный формат DATABASE_URL для PostgreSQL: {DATABASE_URL[:50]}...")
    
    print("Используется PostgreSQL")
    print(f"DATABASE_URL: {DATABASE_URL[:50]}..." if len(DATABASE_URL) > 50 else f"DATABASE_URL: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)
else:
    # Использование SQLite (по умолчанию, не требует установки)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./minsk_jobs.db")
    print("Используется SQLite")
    print("ВНИМАНИЕ: SQLite на Render теряет данные при перезапуске")
    print(f"DATABASE_URL: {DATABASE_URL}")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}  # Нужно для SQLite с FastAPI
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


DEFAULT_TERMS_VERSION = "v1"
DEFAULT_TERMS_TITLE = "Условия пользования сервисом"
DEFAULT_TERMS_CONTENT = """1. Общие положения
Сервис предоставляет площадку для публикации объявлений между пользователями. Администрация не является стороной сделок между пользователями.

2. Ответственность пользователей
Пользователь самостоятельно проверяет достоверность информации, законность задач и контрагентов.
Запрещено публиковать незаконный, вводящий в заблуждение или вредоносный контент.

3. Ограничение ответственности администрации
Администрация не несет ответственности за убытки, ущерб, травмы, претензии третьих лиц,
возникшие при взаимодействии пользователей, исполнении задач, переводе денежных средств,
использовании контактных данных или иных действиях вне технической платформы.

4. Модерация
Администрация вправе ограничивать доступ, удалять объявления и блокировать пользователей
при нарушении правил, требований закона или при риске причинения вреда.

5. Принятие условий
Продолжая использование сервиса после нажатия кнопки принятия, пользователь подтверждает,
что ознакомился с условиями и принимает их в полном объеме.
"""


def get_db():
    """Dependency для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_users_columns(conn):
    inspector = inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("users")}
    dialect = conn.dialect.name

    if "role" not in columns:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"))

    if "is_banned" not in columns:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT 0"))

    if "ban_reason" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN ban_reason TEXT"))

    if "banned_at" not in columns:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE users ADD COLUMN banned_at TIMESTAMPTZ"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN banned_at DATETIME"))

    if "accepted_terms_version" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN accepted_terms_version VARCHAR"))

    if "accepted_terms_at" not in columns:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE users ADD COLUMN accepted_terms_at TIMESTAMPTZ"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN accepted_terms_at DATETIME"))


def _ensure_schema_upgrades():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    with engine.begin() as conn:
        _ensure_users_columns(conn)


def _ensure_default_terms_document():
    from .models import TermsDocument

    db = SessionLocal()
    try:
        active_terms = (
            db.query(TermsDocument)
            .filter(TermsDocument.is_active.is_(True))
            .first()
        )
        if active_terms:
            return

        newest = (
            db.query(TermsDocument)
            .order_by(TermsDocument.created_at.desc(), TermsDocument.id.desc())
            .first()
        )
        if newest:
            newest.is_active = True
            db.commit()
            return

        terms = TermsDocument(
            version=DEFAULT_TERMS_VERSION,
            title=DEFAULT_TERMS_TITLE,
            content=DEFAULT_TERMS_CONTENT.strip(),
            is_active=True,
        )
        db.add(terms)
        db.commit()
    finally:
        db.close()


def init_db():
    """Создание всех таблиц в базе данных"""
    try:
        print("=" * 50)
        print(f"Используется {DB_TYPE.upper()}")
        print(f"DATABASE_URL: {DATABASE_URL[:50]}..." if len(DATABASE_URL) > 50 else f"DATABASE_URL: {DATABASE_URL}")
        
        # Проверяем подключение
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("Подключение к базе данных успешно")
        
        # Создаем таблицы
        Base.metadata.create_all(bind=engine)
        _ensure_schema_upgrades()
        _ensure_default_terms_document()
        print(f"База данных инициализирована: {DB_TYPE.upper()}")
        
        # Проверяем количество данных в БД (только для PostgreSQL)
        if DB_TYPE == "postgresql":
            try:
                with engine.connect() as conn:
                    # Проверяем количество пользователей
                    users_result = conn.execute(text("SELECT COUNT(*) FROM users"))
                    users_count = users_result.scalar()
                    print(f"Пользователей в БД: {users_count}")
                    
                    # Проверяем количество объявлений
                    listings_result = conn.execute(text("SELECT COUNT(*) FROM listings"))
                    listings_count = listings_result.scalar()
                    print(f"Всего объявлений в БД: {listings_count}")
                    
                    # Проверяем активные объявления
                    active_result = conn.execute(text("SELECT COUNT(*) FROM listings WHERE status = 'active'"))
                    active_count = active_result.scalar()
                    print(f"Активных объявлений: {active_count}")
            except Exception as e:
                print(f"Не удалось проверить данные в БД: {e}")
        
        print("=" * 50)
    except Exception as e:
        print(f"Ошибка инициализации базы данных: {e}")
        import traceback
        traceback.print_exc()
        raise

