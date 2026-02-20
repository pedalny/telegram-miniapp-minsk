from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Optional
import hmac
import hashlib
import json
import os
from urllib.parse import unquote
from dotenv import load_dotenv

# Импортируем JSON хранилище вместо БД
from .json_storage import (
    get_user_by_telegram_id,
    create_user,
    get_listings as get_listings_from_storage,
    create_listing as create_listing_in_storage,
    get_listing_by_id,
    get_user_listings,
    update_listing_status,
    get_stats,
    get_all_data,
    get_file_info
)
from .schemas import ListingCreate

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
    init_data: str = Header(..., alias="X-Telegram-Init-Data")
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
    user = get_user_by_telegram_id(telegram_id)
    
    if not user:
        user = create_user(telegram_id, username)
    elif username and user.get("username") != username:
        # Обновляем username если изменился
        from .json_storage import update_user_username
        update_user_username(user["id"], username)
        user["username"] = username
    
    return {
        "user_id": user["id"],
        "telegram_id": user["telegram_id"],
        "username": user.get("username")
    }


@router.get("/api/listings")
async def get_listings(
    type: Optional[str] = None,
    status: str = "active"
):
    """
    Получить все активные объявления (или фильтр по типу)
    """
    listings = get_listings_from_storage(listing_type=type, status=status)
    
    print(f"📊 Запрос объявлений: найдено {len(listings)} активных объявлений (статус='{status}')")
    if listings:
        for listing in listings:
            print(f"  - ID={listing['id']}, тип={listing['type']}, заголовок={listing['title'][:30]}..., пользователь_id={listing['user_id']}")
    else:
        print("  ⚠️  Объявлений не найдено")
    
    # Добавляем username к каждому объявлению
    result = []
    for listing in listings:
        user = get_user_by_id(listing["user_id"])
        result.append({
            "id": listing["id"],
            "type": listing["type"],
            "title": listing["title"],
            "description": listing["description"],
            "address": listing["address"],
            "payment": listing["payment"],
            "contacts": listing["contacts"],
            "latitude": listing["latitude"],
            "longitude": listing["longitude"],
            "username": user.get("username") if user else None,
            "created_at": listing.get("created_at")
        })
    
    return result


@router.post("/api/listings")
async def create_listing(
    listing: ListingCreate,
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
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
        user = get_user_by_telegram_id(telegram_id)

        if not user:
            user = create_user(telegram_id, username)
    else:
        # Локальное тестирование без Telegram
        telegram_id = 999999999
        user = get_user_by_telegram_id(telegram_id)
        if not user:
            user = create_user(telegram_id, "local_test")
    
    if listing.type not in ["task", "worker"]:
        raise HTTPException(status_code=400, detail="Тип должен быть 'task' или 'worker'")
    
    try:
        # Создаем объявление
        db_listing = create_listing_in_storage(
            user_id=user["id"],
            listing_type=listing.type,
            title=listing.title,
            description=listing.description,
            address=listing.address,
            payment=listing.payment,
            contacts=listing.contacts,
            latitude=listing.latitude,
            longitude=listing.longitude,
            status="active"
        )
        
        print(f"✅ Объявление создано: ID={db_listing['id']}, тип={db_listing['type']}, заголовок={db_listing['title']}")
        print(f"📍 Координаты: lat={db_listing['latitude']}, lng={db_listing['longitude']}")
        print(f"👤 Пользователь ID: {user['id']}, telegram_id: {user['telegram_id']}")
        
        # Проверяем, что объявление действительно сохранено
        check_listing = get_listing_by_id(db_listing["id"])
        if check_listing:
            print(f"✅ Проверка: объявление найдено после сохранения, ID={check_listing['id']}")
        else:
            print(f"❌ ОШИБКА: объявление НЕ найдено после сохранения!")
        
        return {
            "id": db_listing["id"],
            "type": db_listing["type"],
            "title": db_listing["title"],
            "status": db_listing["status"]
        }
    except Exception as e:
        print(f"❌ Ошибка при сохранении объявления: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения объявления: {str(e)}")


@router.get("/api/listings/my")
async def get_my_listings(
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
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
        user = get_user_by_telegram_id(telegram_id)
    else:
        telegram_id = 999999999
        user = get_user_by_telegram_id(telegram_id)
    
    if not user:
        return []
    
    listings = get_user_listings(user["id"], status="active")
    
    result = []
    for listing in listings:
        result.append({
            "id": listing["id"],
            "type": listing["type"],
            "title": listing["title"],
            "description": listing["description"],
            "address": listing["address"],
            "payment": listing["payment"],
            "contacts": listing["contacts"],
            "latitude": listing["latitude"],
            "longitude": listing["longitude"],
            "created_at": listing.get("created_at")
        })
    
    return result


@router.delete("/api/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
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
        user = get_user_by_telegram_id(telegram_id)
    else:
        telegram_id = 999999999
        user = get_user_by_telegram_id(telegram_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    listing = get_listing_by_id(listing_id)
    
    if not listing:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    
    if listing["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Нет доступа к этому объявлению")
    
    update_listing_status(listing_id, "closed")
    
    return {"message": "Объявление снято с публикации"}


@router.get("/api/listings/{listing_id}")
async def get_listing(listing_id: int):
    """
    Получить одно объявление по ID
    """
    listing = get_listing_by_id(listing_id)
    
    if not listing or listing.get("status") != "active":
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    
    user = get_user_by_id(listing["user_id"])
    
    return {
        "id": listing["id"],
        "type": listing["type"],
        "title": listing["title"],
        "description": listing["description"],
        "address": listing["address"],
        "payment": listing["payment"],
        "contacts": listing["contacts"],
        "latitude": listing["latitude"],
        "longitude": listing["longitude"],
        "username": user.get("username") if user else None,
        "created_at": listing.get("created_at")
    }


@router.get("/api/admin/data")
async def get_all_data_endpoint():
    """
    Получить все данные из JSON файла (для просмотра состояния)
    ВАЖНО: В продакшене лучше защитить этот endpoint паролем!
    """
    try:
        data = get_all_data()
        file_info = get_file_info()
        return {
            "file_info": file_info,
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения данных: {str(e)}")


@router.get("/api/admin/stats")
async def get_stats_endpoint():
    """
    Получить статистику и информацию о файле данных
    """
    try:
        file_info = get_file_info()
        return file_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения статистики: {str(e)}")
