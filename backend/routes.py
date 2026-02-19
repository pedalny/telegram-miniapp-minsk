from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import hmac
import hashlib
import json
import os
from urllib.parse import unquote
from dotenv import load_dotenv

# Импортируем из текущего пакета backend
from .database import get_db
from .models import User, Listing
from .schemas import UserCreate, ListingCreate, ListingResponse

load_dotenv()

router = APIRouter()


def verify_telegram_webapp_data(init_data: str) -> Optional[dict]:
    """
    Проверка подлинности данных от Telegram WebApp
    """
    try:
        # Парсим данные
        data_pairs = {}
        for pair in init_data.split('&'):
            if '=' not in pair:
                continue
            key, value = pair.split('=', 1)
            # URL декодируем значение
            data_pairs[key] = unquote(value)

        # Извлекаем hash и user данные
        received_hash = data_pairs.pop('hash', '')
        user_data_str = data_pairs.get('user', '')
        
        if not user_data_str:
            return None

        # Создаем строку для проверки (без hash)
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(data_pairs.items())])
        
        # Получаем секретный ключ из токена бота
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            print("Предупреждение: TELEGRAM_BOT_TOKEN не установлен")
            return None
            
        secret_key = hmac.new(
            "WebAppData".encode(),
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        # Вычисляем hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Проверяем
        if calculated_hash != received_hash:
            print(f"Hash не совпадает. Получен: {received_hash[:10]}..., Вычислен: {calculated_hash[:10]}...")
            return None
        
        # Парсим user данные
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
    """
    user_data = verify_telegram_webapp_data(init_data)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Неверные данные Telegram")
    
    telegram_id = user_data.get("id")
    username = user_data.get("username")
    
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Отсутствует telegram_id")
    
    # Ищем или создаем пользователя
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
    """
    query = db.query(Listing).filter(Listing.status == status)
    
    if type:
        query = query.filter(Listing.type == type)
    
    listings = query.all()
    
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
    """
    user = None

    if init_data:
        # Боевой режим — проверяем подпись Telegram
        user_data = verify_telegram_webapp_data(init_data)
        if not user_data:
            raise HTTPException(status_code=401, detail="Неверные данные Telegram")

        telegram_id = user_data.get("id")
        username = user_data.get("username")
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            user = User(telegram_id=telegram_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)
    else:
        # Локальное тестирование без Telegram
        telegram_id = 999999999
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id, username="local_test")
            db.add(user)
            db.commit()
            db.refresh(user)
    
    if listing.type not in ["task", "worker"]:
        raise HTTPException(status_code=400, detail="Тип должен быть 'task' или 'worker'")
    
    # Создаем объявление
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
    
    return {
        "id": db_listing.id,
        "type": db_listing.type,
        "title": db_listing.title,
        "status": db_listing.status
    }


@router.get("/api/listings/my")
async def get_my_listings(
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db)
):
    """
    Получить все объявления текущего пользователя.
    - В Telegram Mini App используется проверка initData.
    - Для локального тестирования используется тестовый пользователь.
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
    
    listing = db.query(Listing).filter(
        Listing.id == listing_id,
        Listing.user_id == user.id
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    
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

