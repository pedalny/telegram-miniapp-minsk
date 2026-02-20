"""
Модуль для работы с данными в JSON файле
"""
import json
import os
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Путь к файлу данных
# На Render используем текущую директорию (постоянное хранилище)
# Можно переопределить через переменные окружения DATA_DIR и DATA_FILE
DATA_FILE = os.getenv("DATA_FILE", "data.json")
DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(DATA_DIR, DATA_FILE)

# Блокировка для потокобезопасной записи
_file_lock = threading.Lock()


def _ensure_data_file():
    """Создает файл данных если его нет"""
    if not os.path.exists(DATA_PATH):
        initial_data = {
            "users": [],
            "listings": [],
            "next_user_id": 1,
            "next_listing_id": 1
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)
        print(f"📁 Создан файл данных: {DATA_PATH}")


def _load_data() -> Dict[str, Any]:
    """Загружает данные из JSON файла"""
    _ensure_data_file()
    with _file_lock:
        try:
            with open(DATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Если файл поврежден, создаем новый
            _ensure_data_file()
            return _load_data()


def _save_data(data: Dict[str, Any]):
    """Сохраняет данные в JSON файл"""
    with _file_lock:
        # Создаем временный файл для атомарной записи
        temp_path = DATA_PATH + ".tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Атомарно заменяем старый файл новым
        os.replace(temp_path, DATA_PATH)


# ========== Работа с пользователями ==========

def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Находит пользователя по telegram_id"""
    data = _load_data()
    for user in data["users"]:
        if user["telegram_id"] == telegram_id:
            return user
    return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Находит пользователя по id"""
    data = _load_data()
    for user in data["users"]:
        if user["id"] == user_id:
            return user
    return None


def create_user(telegram_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    """Создает нового пользователя"""
    data = _load_data()
    
    # Проверяем, не существует ли уже
    existing = get_user_by_telegram_id(telegram_id)
    if existing:
        # Обновляем username если изменился
        if username and existing.get("username") != username:
            existing["username"] = username
            _save_data(data)
        return existing
    
    # Создаем нового
    user = {
        "id": data["next_user_id"],
        "telegram_id": telegram_id,
        "username": username,
        "created_at": datetime.now().isoformat()
    }
    
    data["users"].append(user)
    data["next_user_id"] += 1
    _save_data(data)
    
    return user


def update_user_username(user_id: int, username: str):
    """Обновляет username пользователя"""
    data = _load_data()
    for user in data["users"]:
        if user["id"] == user_id:
            user["username"] = username
            _save_data(data)
            return


# ========== Работа с объявлениями ==========

def create_listing(
    user_id: int,
    listing_type: str,
    title: str,
    description: str,
    address: str,
    payment: str,
    contacts: str,
    latitude: float,
    longitude: float,
    status: str = "active"
) -> Dict[str, Any]:
    """Создает новое объявление"""
    data = _load_data()
    
    listing = {
        "id": data["next_listing_id"],
        "user_id": user_id,
        "type": listing_type,
        "title": title,
        "description": description,
        "address": address,
        "payment": payment,
        "contacts": contacts,
        "latitude": latitude,
        "longitude": longitude,
        "status": status,
        "created_at": datetime.now().isoformat()
    }
    
    data["listings"].append(listing)
    data["next_listing_id"] += 1
    _save_data(data)
    
    return listing


def get_listing_by_id(listing_id: int) -> Optional[Dict[str, Any]]:
    """Находит объявление по id"""
    data = _load_data()
    for listing in data["listings"]:
        if listing["id"] == listing_id:
            return listing
    return None


def get_listings(
    listing_type: Optional[str] = None,
    status: str = "active",
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Получает список объявлений с фильтрами"""
    data = _load_data()
    listings = data["listings"]
    
    # Фильтруем по статусу
    filtered = [l for l in listings if l.get("status") == status]
    
    # Фильтруем по типу
    if listing_type:
        filtered = [l for l in filtered if l.get("type") == listing_type]
    
    # Фильтруем по пользователю
    if user_id:
        filtered = [l for l in filtered if l.get("user_id") == user_id]
    
    return filtered


def update_listing_status(listing_id: int, status: str):
    """Обновляет статус объявления"""
    data = _load_data()
    for listing in data["listings"]:
        if listing["id"] == listing_id:
            listing["status"] = status
            _save_data(data)
            return True
    return False


def get_user_listings(user_id: int, status: str = "active") -> List[Dict[str, Any]]:
    """Получает объявления пользователя"""
    return get_listings(status=status, user_id=user_id)


def get_stats() -> Dict[str, int]:
    """Получает статистику по данным"""
    data = _load_data()
    return {
        "users_count": len(data["users"]),
        "listings_count": len(data["listings"]),
        "active_listings_count": len([l for l in data["listings"] if l.get("status") == "active"])
    }

