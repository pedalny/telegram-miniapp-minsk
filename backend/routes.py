from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import hmac
import hashlib
import json
import os
from urllib.parse import unquote
from dotenv import load_dotenv

# Импортируем БД (PostgreSQL для продакшена, SQLite для локальной разработки)
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Listing
from .schemas import ListingCreate

load_dotenv()

router = APIRouter()


def verify_telegram_webapp_data(init_data: str) -> Optional[dict]:
    """
    Проверка подлинности данных от Telegram WebApp
    
    Telegram отправляет данные в формате query string с подписью (hash).
    Эта функция проверяет подпись, чтобы убедиться, что данные действительно от Telegram.
    
    Процесс проверки:
    1. Парсит query string и извлекает hash
    2. Создает строку для проверки из всех параметров кроме hash
    3. Вычисляет секретный ключ из токена бота
    4. Вычисляет hash от строки проверки
    5. Сравнивает вычисленный hash с полученным
    
    Args:
        init_data: Строка с данными от Telegram (формат: "user=...&hash=...")
        
    Returns:
        Словарь с данными пользователя если проверка успешна, None если неверные данные
        
    Security:
        Использует HMAC-SHA256 для проверки подписи
        Защищает от подделки данных злоумышленниками
    """
    try:
        # Шаг 1: Парсим query string (формат: "key1=value1&key2=value2&hash=...")
        data_pairs = {}
        for pair in init_data.split('&'):
            if '=' not in pair:
                continue
            key, value = pair.split('=', 1)
            # URL декодируем значение (Telegram кодирует специальные символы)
            data_pairs[key] = unquote(value)

        # Шаг 2: Извлекаем hash (подпись) и данные пользователя
        received_hash = data_pairs.pop('hash', '')  # Удаляем hash из словаря
        user_data_str = data_pairs.get('user', '')
        
        if not user_data_str:
            return None

        # Шаг 3: Создаем строку для проверки (все параметры кроме hash, отсортированные)
        # Формат: "key1=value1\nkey2=value2\n..." (каждая пара на новой строке)
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(data_pairs.items())])
        
        # Шаг 4: Получаем секретный ключ из токена бота
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            print("Предупреждение: TELEGRAM_BOT_TOKEN не установлен")
            return None
        
        # Вычисляем секретный ключ: HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            "WebAppData".encode(),
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        # Шаг 5: Вычисляем hash от строки проверки
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Шаг 6: Сравниваем вычисленный hash с полученным
        if calculated_hash != received_hash:
            print(f"Hash не совпадает. Получен: {received_hash[:10]}..., Вычислен: {calculated_hash[:10]}...")
            return None
        
        # Шаг 7: Если проверка успешна, парсим данные пользователя из JSON
        user_data = json.loads(user_data_str)
        return user_data
        
    except Exception as e:
        print(f"Ошибка проверки Telegram данных: {e}")
        import traceback
        traceback.print_exc()
        return None


@router.post("/api/auth/telegram")
async def auth_telegram(
    init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db)
):
    """
    Авторизация через Telegram WebApp
    
    Проверяет подпись данных от Telegram и создает/находит пользователя в системе.
    Используется при первом открытии приложения в Telegram.
    
    Args:
        init_data: Данные от Telegram WebApp (в заголовке X-Telegram-Init-Data)
        db: Сессия базы данных
        
    Returns:
        {
            "user_id": int,           # Внутренний ID пользователя
            "telegram_id": int,        # Telegram ID пользователя
            "username": str            # Имя пользователя (может быть None)
        }
        
    Raises:
        HTTPException 401: Если данные Telegram неверны или не прошли проверку подписи
        HTTPException 400: Если отсутствует telegram_id в данных
    """
    user_data = verify_telegram_webapp_data(init_data)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Неверные данные Telegram")
    
    telegram_id = user_data.get("id")
    username = user_data.get("username")
    
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Отсутствует telegram_id")
    
    # Ищем или создаем пользователя в БД
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif username and user.username != username:
        # Обновляем username если изменился
        user.username = username
        db.commit()
    
    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username
    }


@router.get("/api/listings")
async def get_listings(
    db: Session = Depends(get_db),
    type: Optional[str] = None,
    status: str = "active"
):
    """
    Получить все активные объявления (или фильтр по типу)
    
    Используется для загрузки всех объявлений на карту.
    Поддерживает фильтрацию по типу (task/worker) и статусу.
    
    Args:
        db: Сессия базы данных
        type: Тип объявления ("task" или "worker"), None = все типы
        status: Статус объявления ("active" или "closed"), по умолчанию "active"
        
    Returns:
        Список объявлений, каждое содержит:
        {
            "id": int,
            "type": str,              # "task" или "worker"
            "title": str,
            "description": str,
            "address": str,
            "payment": str,
            "contacts": str,
            "latitude": float,
            "longitude": float,
            "username": str,          # Имя пользователя-автора
            "created_at": str         # ISO формат даты
        }
    """
    # Строим запрос с фильтрами
    query = db.query(Listing).filter(Listing.status == status)
    
    if type:
        query = query.filter(Listing.type == type)
    
    listings = query.all()
    
    print(f"📊 Запрос объявлений: найдено {len(listings)} активных объявлений (статус='{status}')")
    if listings:
        for listing in listings:
            print(f"  - ID={listing.id}, тип={listing.type}, заголовок={listing.title[:30]}..., пользователь_id={listing.user_id}")
    else:
        print("  ⚠️  Объявлений не найдено")
    
    # Формируем результат
    result = []
    for listing in listings:
        result.append({
            "id": listing.id,
            "type": listing.type,
            "title": listing.title,
            "description": listing.description,
            "address": listing.address,
            "payment": listing.payment,
            "contacts": listing.contacts,
            "latitude": listing.latitude,
            "longitude": listing.longitude,
            "username": listing.user.username if listing.user else None,
            "created_at": listing.created_at.isoformat() if listing.created_at else None
        })
    
    return result


@router.post("/api/listings")
async def create_listing(
    listing: ListingCreate,
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db)
):
    """
    Создать новое объявление (задачу или исполнителя).
    - В Telegram Mini App используется проверка initData.
    - При локальном тестировании (без Telegram) создаётся/используется тестовый пользователь.
    
    Args:
        listing: Данные объявления (тип, заголовок, описание, адрес, оплата, контакты, координаты)
        init_data: Данные от Telegram WebApp (опционально, для локального тестирования)
        db: Сессия базы данных
        
    Returns:
        {
            "id": int,           # ID созданного объявления
            "type": str,          # Тип объявления
            "title": str,         # Заголовок
            "status": str         # Статус ("active")
        }
    """
    print("=" * 50)
    print("📥 Получен запрос на создание объявления")
    print(f"   Тип: {listing.type}")
    print(f"   Заголовок: {listing.title}")
    print(f"   Координаты: lat={listing.latitude}, lng={listing.longitude}")
    print(f"   Init Data: {'есть' if init_data else 'нет (локальный режим)'}")
    
    user = None

    if init_data:
        # Боевой режим — проверяем подпись Telegram
        print("🔐 Проверка данных Telegram...")
        user_data = verify_telegram_webapp_data(init_data)
        if not user_data:
            print("❌ Ошибка проверки Telegram данных")
            raise HTTPException(status_code=401, detail="Неверные данные Telegram")

        telegram_id = user_data.get("id")
        username = user_data.get("username")
        print(f"👤 Telegram ID: {telegram_id}, Username: {username}")
        
        # Ищем или создаем пользователя в БД
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            print("➕ Создание нового пользователя...")
            user = User(telegram_id=telegram_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            print(f"✅ Пользователь найден: ID={user.id}")
    else:
        # Локальное тестирование без Telegram
        print("🧪 Локальный режим тестирования")
        telegram_id = 999999999
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            print("➕ Создание тестового пользователя...")
            user = User(telegram_id=telegram_id, username="local_test")
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            print(f"✅ Тестовый пользователь найден: ID={user.id}")
    
    if listing.type not in ["task", "worker"]:
        raise HTTPException(status_code=400, detail="Тип должен быть 'task' или 'worker'")
    
    try:
        # Создаем объявление в БД
        db_listing = Listing(
            user_id=user.id,
            type=listing.type,
            title=listing.title,
            description=listing.description,
            address=listing.address,
            payment=listing.payment,
            contacts=listing.contacts,
            latitude=listing.latitude,
            longitude=listing.longitude,
            status="active"
        )
        
        db.add(db_listing)
        db.commit()
        db.refresh(db_listing)
        
        print(f"✅ Объявление создано: ID={db_listing.id}, тип={db_listing.type}, заголовок={db_listing.title}")
        print(f"📍 Координаты: lat={db_listing.latitude}, lng={db_listing.longitude}")
        print(f"👤 Пользователь ID: {user.id}, telegram_id: {user.telegram_id}")
        
        # Проверяем, что объявление действительно сохранено в БД
        check_listing = db.query(Listing).filter(Listing.id == db_listing.id).first()
        if check_listing:
            print(f"✅ Проверка: объявление найдено в БД после сохранения, ID={check_listing.id}")
        else:
            print(f"❌ ОШИБКА: объявление НЕ найдено в БД после сохранения!")
        
        return {
            "id": db_listing.id,
            "type": db_listing.type,
            "title": db_listing.title,
            "status": db_listing.status
        }
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при сохранении объявления: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения объявления: {str(e)}")


@router.get("/api/listings/my")
async def get_my_listings(
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db)
):
    """
    Получить все объявления текущего пользователя.
    - В Telegram Mini App используется проверка initData.
    - Для локального тестирования используется тестовый пользователь.
    
    Args:
        init_data: Данные от Telegram WebApp (опционально)
        db: Сессия базы данных
        
    Returns:
        Список объявлений текущего пользователя
    """
    user = None

    if init_data:
        user_data = verify_telegram_webapp_data(init_data)
        if not user_data:
            raise HTTPException(status_code=401, detail="Неверные данные Telegram")
        telegram_id = user_data.get("id")
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
    else:
        telegram_id = 999999999
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
    
    if not user:
        return []
    
    # Получаем объявления пользователя
    listings = db.query(Listing).filter(
        Listing.user_id == user.id,
        Listing.status == "active"
    ).all()
    
    result = []
    for listing in listings:
        result.append({
            "id": listing.id,
            "type": listing.type,
            "title": listing.title,
            "description": listing.description,
            "address": listing.address,
            "payment": listing.payment,
            "contacts": listing.contacts,
            "latitude": listing.latitude,
            "longitude": listing.longitude,
            "created_at": listing.created_at.isoformat() if listing.created_at else None
        })
    
    return result


@router.delete("/api/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db)
):
    """
    Удалить (снять) объявление.
    
    Не удаляет объявление физически, а меняет статус на "closed".
    Это позволяет сохранить историю объявлений.
    
    Args:
        listing_id: ID объявления для удаления
        init_data: Данные от Telegram WebApp (опционально)
        db: Сессия базы данных
        
    Returns:
        {"message": "Объявление снято с публикации"}
        
    Raises:
        HTTPException 404: Если пользователь или объявление не найдены
        HTTPException 403: Если пользователь не является автором объявления
    """
    user = None

    if init_data:
        user_data = verify_telegram_webapp_data(init_data)
        if not user_data:
            raise HTTPException(status_code=401, detail="Неверные данные Telegram")
        telegram_id = user_data.get("id")
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
    else:
        telegram_id = 999999999
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Ищем объявление
    listing = db.query(Listing).filter(
        Listing.id == listing_id,
        Listing.user_id == user.id
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    
    # Меняем статус на "closed" вместо физического удаления
    listing.status = "closed"
    db.commit()
    
    return {"message": "Объявление снято с публикации"}


@router.get("/api/listings/{listing_id}")
async def get_listing(
    listing_id: int,
    db: Session = Depends(get_db)
):
    """
    Получить одно объявление по ID
    
    Args:
        listing_id: ID объявления
        db: Сессия базы данных
        
    Returns:
        Данные объявления с информацией об авторе
        
    Raises:
        HTTPException 404: Если объявление не найдено или неактивно
    """
    listing = db.query(Listing).filter(
        Listing.id == listing_id,
        Listing.status == "active"
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    
    return {
        "id": listing.id,
        "type": listing.type,
        "title": listing.title,
        "description": listing.description,
        "address": listing.address,
        "payment": listing.payment,
        "contacts": listing.contacts,
        "latitude": listing.latitude,
        "longitude": listing.longitude,
        "username": listing.user.username if listing.user else None,
        "created_at": listing.created_at.isoformat() if listing.created_at else None
    }
