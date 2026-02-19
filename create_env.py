#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

# Определяем путь к директории скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

content = """# Тип базы данных: sqlite или postgresql
# По умолчанию используется SQLite (не требует установки)
DB_TYPE=sqlite

# Для SQLite (по умолчанию) - файл создастся автоматически
DATABASE_URL=sqlite:///./minsk_jobs.db

# Telegram Bot Token (получите от @BotFather)
# Пока оставьте пустым, заполните после создания бота
TELEGRAM_BOT_TOKEN=

# Яндекс.Карты API ключ
# Пока оставьте пустым, заполните после получения ключа
YANDEX_MAPS_API_KEY=

# Секретный ключ для подписи (любая случайная строка)
# Сгенерируйте случайную строку для безопасности
SECRET_KEY=change_this_to_random_string_in_production
"""

with open(env_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Файл .env создан успешно в: {env_path}')

