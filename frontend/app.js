// Глобальные переменные
// Leaflet карта
let map;
let currentMode = null; // 'task' или 'worker'
let currentCoords = null;
let currentAddress = null;
let tempMarker = null; // временный маркер при постановке
let markers = [];      // маркеры всех объявлений
let userInfo = null;

// Инициализация Telegram WebApp
let tg = null;
let isTelegramWebApp = false;

try {
    if (window.Telegram && window.Telegram.WebApp) {
        tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        isTelegramWebApp = true;
    }
} catch (e) {
    console.log('Telegram WebApp недоступен (локальное тестирование)');
}

// Инициализация приложения
document.addEventListener('DOMContentLoaded', async () => {
    // Получаем API ключ из конфига (в продакшене лучше через env)
    // Пока что нужно будет заменить в index.html
    await initAuth();
    await initMap();
    await loadListings();
});

// Авторизация через Telegram
async function initAuth() {
    if (!isTelegramWebApp || !tg || !tg.initData) {
        console.log('Режим локального тестирования - авторизация пропущена');
        // Для локального тестирования можно создать мок пользователя
        userInfo = { telegram_id: 123456789, username: 'test_user' };
        return;
    }
    
    try {
        const initData = tg.initData;
        
        if (!initData) {
            console.warn('initData пуст');
            return;
        }
        
        const response = await fetch('/api/auth/telegram', {
            method: 'POST',
            headers: {
                'X-Telegram-Init-Data': initData
            }
        });
        
        if (response.ok) {
            userInfo = await response.json();
            console.log('Авторизован:', userInfo);
        } else {
            const error = await response.json();
            console.error('Ошибка авторизации:', error);
        }
    } catch (error) {
        console.error('Ошибка при авторизации:', error);
    }
}

// Инициализация карты Leaflet (OpenStreetMap)
function initMap() {
    return new Promise((resolve) => {
        if (typeof L === 'undefined') {
            console.error('Leaflet не загружен. Проверьте подключение в index.html');
            return;
        }

        // Центр на Минск
        map = L.map('map').setView([53.9045, 27.5615], 11);

        // Подложка OpenStreetMap
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors'
        }).addTo(map);

        // Обработчик клика по карте
        // Адрес пользователь вводит сам в форме, мы только запоминаем координаты.
        map.on('click', (e) => {
            if (!currentMode) return;

            const { lat, lng } = e.latlng;
            currentCoords = [lat, lng];

            // Удаляем предыдущий временный маркер
            if (tempMarker) {
                map.removeLayer(tempMarker);
            }

            // Создаем временный маркер
            const markerColor = currentMode === 'task' ? 'red' : 'green';
            const icon = L.divIcon({
                className: 'custom-marker',
                html: `<div style="width:18px;height:18px;border-radius:50%;background:${markerColor};border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.5);"></div>`,
                iconSize: [18, 18],
                iconAnchor: [9, 9]
            });

            tempMarker = L.marker([lat, lng], { draggable: true, icon }).addTo(map);

            // При перетаскивании обновляем координаты
            tempMarker.on('dragend', (event) => {
                const pos = event.target.getLatLng();
                currentCoords = [pos.lat, pos.lng];
            });

            // Показываем форму (адрес вводится вручную)
            hideHint();
            if (currentMode === 'task') {
                document.getElementById('taskModal').classList.add('active');
            } else {
                document.getElementById('workerModal').classList.add('active');
            }
        });

        resolve();
    });
}

// Начало размещения задачи
function startPlaceTask() {
    currentMode = 'task';
    showHint('Нажмите на карте, где будет работа');
}

// Начало размещения исполнителя
function startPlaceWorker() {
    currentMode = 'worker';
    showHint('Нажмите на карте, где вам удобно работать');
}

// Показать подсказку
function showHint(text) {
    const hint = document.getElementById('hint');
    hint.textContent = text;
    hint.classList.add('active');
}

// Скрыть подсказку
function hideHint() {
    document.getElementById('hint').classList.remove('active');
}

// Закрыть модальное окно
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
    currentMode = null;
    currentCoords = null;
    currentAddress = null;
    
    if (tempMarker) {
        map.removeLayer(tempMarker);
        tempMarker = null;
    }
}

// Отправка задачи
async function submitTask(event) {
    event.preventDefault();
    
    if (!currentCoords) {
        alert('Выберите место на карте');
        return;
    }
    
    const data = {
        type: 'task',
        title: document.getElementById('taskTitle').value,
        description: document.getElementById('taskDescription').value,
        address: document.getElementById('taskAddress').value,
        payment: document.getElementById('taskPayment').value,
        contacts: document.getElementById('taskContacts').value,
        latitude: currentCoords[0],
        longitude: currentCoords[1]
    };
    
    try {
        const headers = {
            'Content-Type': 'application/json'
        };
        if (isTelegramWebApp && tg && tg.initData) {
            headers['X-Telegram-Init-Data'] = tg.initData;
        }

        const response = await fetch('/api/listings', {
            method: 'POST',
            headers,
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const result = await response.json();
            alert('Задача опубликована!');
            closeModal('taskModal');
            document.getElementById('taskForm').reset();
            await loadListings();
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.detail || 'Не удалось опубликовать'));
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Ошибка при публикации задачи');
    }
}

// Отправка исполнителя
async function submitWorker(event) {
    event.preventDefault();
    
    if (!currentCoords) {
        alert('Выберите место на карте');
        return;
    }
    
    const data = {
        type: 'worker',
        title: document.getElementById('workerTitle').value,
        description: document.getElementById('workerDescription').value,
        address: document.getElementById('workerAddress').value,
        payment: document.getElementById('workerPayment').value,
        contacts: document.getElementById('workerContacts').value,
        latitude: currentCoords[0],
        longitude: currentCoords[1]
    };
    
    try {
        const headers = {
            'Content-Type': 'application/json'
        };
        if (isTelegramWebApp && tg && tg.initData) {
            headers['X-Telegram-Init-Data'] = tg.initData;
        }

        const response = await fetch('/api/listings', {
            method: 'POST',
            headers,
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const result = await response.json();
            alert('Объявление опубликовано!');
            closeModal('workerModal');
            document.getElementById('workerForm').reset();
            await loadListings();
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.detail || 'Не удалось опубликовать'));
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Ошибка при публикации объявления');
    }
}

// Загрузка всех объявлений
async function loadListings() {
    try {
        const response = await fetch('/api/listings');
        const listings = await response.json();
        
        // Удаляем старые маркеры
        markers.forEach(marker => {
            map.removeLayer(marker);
        });
        markers = [];
        
        // Добавляем новые маркеры
        listings.forEach(listing => {
            const color = listing.type === 'task' ? 'red' : 'green';
            const icon = L.divIcon({
                className: 'custom-marker',
                html: `<div style="width:18px;height:18px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.5);"></div>`,
                iconSize: [18, 18],
                iconAnchor: [9, 9]
            });

            const marker = L.marker([listing.latitude, listing.longitude], { icon })
                .on('click', () => showListingDetail(listing.id))
                .addTo(map);

            markers.push(marker);
        });
    } catch (error) {
        console.error('Ошибка загрузки объявлений:', error);
    }
}

// Показать детали объявления
async function showListingDetail(listingId) {
    try {
        const response = await fetch(`/api/listings/${listingId}`);
        const listing = await response.json();
        
        const detailDiv = document.getElementById('listingDetail');
        
        if (listing.type === 'task') {
            detailDiv.innerHTML = `
                <h3>🔴 ЗАДАЧА</h3>
                <p><strong>👤 Заказчик:</strong> @${listing.username || 'не указан'}</p>
                <p><strong>📝 Описание:</strong> ${listing.description}</p>
                <p><strong>📍 Адрес:</strong> ${listing.address}</p>
                <p><strong>💰 Оплата:</strong> ${listing.payment}</p>
                <p><strong>📞 Контакты:</strong> ${listing.contacts}</p>
                <button class="btn-contact" onclick="contactUser('${listing.contacts}')">Написать заказчику</button>
            `;
        } else {
            detailDiv.innerHTML = `
                <h3>🟢 ИЩУ РАБОТУ</h3>
                <p><strong>👤 Исполнитель:</strong> @${listing.username || 'не указан'}</p>
                <p><strong>🔧 Что умеет:</strong> ${listing.title}</p>
                <p><strong>📝 Описание:</strong> ${listing.description}</p>
                <p><strong>📍 Готов работать:</strong> ${listing.address}</p>
                <p><strong>💸 Оплата:</strong> ${listing.payment}</p>
                <p><strong>📞 Контакты:</strong> ${listing.contacts}</p>
                <button class="btn-contact" onclick="contactUser('${listing.contacts}')">Написать исполнителю</button>
            `;
        }
        
        document.getElementById('detailModal').classList.add('active');
        
        // Центрируем карту на объявлении
    if (map) {
        map.setView([listing.latitude, listing.longitude], 15);
    }
    } catch (error) {
        console.error('Ошибка загрузки объявления:', error);
        alert('Не удалось загрузить объявление');
    }
}

// Связаться с пользователем
function contactUser(contacts) {
    if (isTelegramWebApp && tg) {
        if (contacts.startsWith('@')) {
            tg.openTelegramLink(`https://t.me/${contacts.substring(1)}`);
        } else if (contacts.startsWith('+') || /^\d/.test(contacts)) {
            tg.openTelegramLink(`https://t.me/${contacts}`);
        } else {
            tg.openTelegramLink(`https://t.me/${contacts}`);
        }
    } else {
        // Для локального тестирования просто показываем контакты
        alert(`Контакты: ${contacts}\n\nВ Telegram здесь будет открыт чат`);
    }
}

// Показать мои объявления
async function showMyListings() {
    if (!isTelegramWebApp || !tg || !tg.initData) {
        alert('Эта функция доступна только в Telegram');
        return;
    }
    
    const initData = tg.initData;
    
    try {
        const response = await fetch('/api/listings/my', {
            headers: {
                'X-Telegram-Init-Data': initData
            }
        });
        
        const listings = await response.json();
        
        const tasks = listings.filter(l => l.type === 'task');
        const workers = listings.filter(l => l.type === 'worker');
        
        renderMyListings(tasks, workers);
        document.getElementById('myListingsModal').classList.add('active');
    } catch (error) {
        console.error('Ошибка загрузки моих объявлений:', error);
        alert('Не удалось загрузить объявления');
    }
}

// Рендер моих объявлений
function renderMyListings(tasks, workers) {
    const content = document.getElementById('myListingsContent');
    const currentTab = document.querySelector('.tab.active').textContent.includes('задачи') ? 'tasks' : 'workers';
    
    const listingsToShow = currentTab === 'tasks' ? tasks : workers;
    
    if (listingsToShow.length === 0) {
        content.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Нет объявлений</p>';
        return;
    }
    
    content.innerHTML = listingsToShow.map(listing => `
        <div class="listing-item">
            <h4>${listing.title}</h4>
            <p>📍 ${listing.address}</p>
            <p>💰 ${listing.payment}</p>
            <p style="margin-top: 8px; color: #999; font-size: 12px;">${listing.description.substring(0, 100)}...</p>
            <button class="btn-remove" onclick="removeListing(${listing.id})">Снять</button>
        </div>
    `).join('');
}

// Переключение вкладок
function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    
    if (!isTelegramWebApp || !tg || !tg.initData) {
        return;
    }
    
    const initData = tg.initData;
    
    fetch('/api/listings/my', {
        headers: {
            'X-Telegram-Init-Data': initData
        }
    })
    .then(r => r.json())
    .then(listings => {
        const tasks = listings.filter(l => l.type === 'task');
        const workers = listings.filter(l => l.type === 'worker');
        renderMyListings(tasks, workers);
    });
}

// Удалить объявление
async function removeListing(listingId) {
    if (!confirm('Снять объявление с публикации?')) {
        return;
    }
    
    if (!isTelegramWebApp || !tg || !tg.initData) {
        alert('Эта функция доступна только в Telegram');
        return;
    }
    
    const initData = tg.initData;
    
    try {
        const response = await fetch(`/api/listings/${listingId}`, {
            method: 'DELETE',
            headers: {
                'X-Telegram-Init-Data': initData
            }
        });
        
        if (response.ok) {
            alert('Объявление снято');
            await loadListings();
            await showMyListings();
        } else {
            alert('Ошибка при удалении');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Ошибка при удалении');
    }
}

