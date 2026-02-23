// Глобальные переменные
// Leaflet карта
let map;
let currentMode = null; // 'task' или 'worker'
let currentCoords = null;
let currentAddress = null;
let tempMarker = null; // временный маркер при постановке
let markers = [];      // маркеры всех объявлений на карте
let mapListings = [];  // все объявления, загруженные для карты
let currentMapFilter = 'all'; // all | task | worker
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
    initMapFilters();
    
    // Проверяем параметры URL для показа конкретного объявления
    const urlParams = new URLSearchParams(window.location.search);
    const showId = urlParams.get('show');
    const lat = urlParams.get('lat');
    const lng = urlParams.get('lng');
    
    if (showId && lat && lng) {
        // Ждём загрузки маркеров
        setTimeout(() => {
            // Центрируем карту на объявлении
            map.setView([parseFloat(lat), parseFloat(lng)], 15);
            
            // Находим маркер и показываем его popup
            const marker = markers.find(m => {
                const listingId = m._listingId;
                return listingId && listingId.toString() === showId;
            });
            
            if (marker) {
                marker.openPopup();
            }
            
            // Очищаем URL от параметров
            window.history.replaceState({}, document.title, '/');
        }, 500);
    }
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
        // Получаем адрес по координатам через обратный геокодинг
        map.on('click', async (e) => {
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

            // Получаем адрес по координатам
            showHint('Получение адреса...');
            const address = await getAddressFromCoords(lat, lng);
            const addressText = address || `Минск, координаты: ${lat.toFixed(6)}, ${lng.toFixed(6)}`;
            
            // Заполняем адрес в форме
            if (currentMode === 'task') {
                document.getElementById('taskAddress').value = addressText;
            } else {
                document.getElementById('workerAddress').value = addressText;
            }

            // При перетаскивании обновляем координаты и адрес
            tempMarker.on('dragend', async (event) => {
                const pos = event.target.getLatLng();
                currentCoords = [pos.lat, pos.lng];
                
                // Обновляем адрес при перемещении
                const newAddress = await getAddressFromCoords(pos.lat, pos.lng);
                const newAddressText = newAddress || `Минск, координаты: ${pos.lat.toFixed(6)}, ${pos.lng.toFixed(6)}`;
                
                if (currentMode === 'task') {
                    document.getElementById('taskAddress').value = newAddressText;
                } else {
                    document.getElementById('workerAddress').value = newAddressText;
                }
            });

            // Показываем форму
            hideHint();
            if (currentMode === 'task') {
                document.getElementById('taskModal').classList.add('active');
            } else {
                document.getElementById('workerModal').classList.add('active');
            }
            
            // Если модальное окно было закрыто для выбора на карте, открываем его снова
            setTimeout(() => {
                if (currentMode === 'task' && !document.getElementById('taskModal').classList.contains('active')) {
                    document.getElementById('taskModal').classList.add('active');
                } else if (currentMode === 'worker' && !document.getElementById('workerModal').classList.contains('active')) {
                    document.getElementById('workerModal').classList.add('active');
                }
            }, 100);
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
    
    // Не сбрасываем currentMode и currentCoords, если это доска объявлений или мои объявления
    if (modalId !== 'boardModal' && modalId !== 'myListingsModal') {
        currentMode = null;
        currentCoords = null;
        currentAddress = null;
        
        if (tempMarker) {
            map.removeLayer(tempMarker);
            tempMarker = null;
        }
    }
}

// Получение адреса по координатам через Nominatim (OpenStreetMap)
async function getAddressFromCoords(lat, lng) {
    try {
        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1&accept-language=ru`,
            {
                headers: {
                    'User-Agent': 'MinskJobsApp/1.0'
                }
            }
        );
        
        if (!response.ok) {
            return null;
        }
        
        const data = await response.json();
        
        if (data && data.address) {
            const addr = data.address;
            let addressParts = [];
            
            // Формируем адрес из компонентов
            if (addr.road) addressParts.push(addr.road);
            if (addr.house_number) addressParts.push(addr.house_number);
            if (addr.suburb || addr.neighbourhood) addressParts.push(addr.suburb || addr.neighbourhood);
            if (addr.city || addr.town) {
                if (!addressParts.includes(addr.city || addr.town)) {
                    addressParts.push(addr.city || addr.town);
                }
            }
            
            if (addressParts.length > 0) {
                return addressParts.join(', ');
            }
            
            // Если не получилось собрать, используем display_name
            if (data.display_name) {
                return data.display_name.split(', ').slice(0, 3).join(', ');
            }
        }
        
        return null;
    } catch (error) {
        console.error('Ошибка получения адреса:', error);
        return null;
    }
}

// Получение геолокации через браузерный Geolocation API
async function getCurrentLocation(formType) {
    if (!navigator.geolocation) {
        alert('Геолокация не поддерживается вашим браузером');
        return;
    }
    
    // Показываем индикатор загрузки
    const hint = document.getElementById('hint');
    hint.textContent = 'Получение геолокации...';
    hint.classList.add('active');
    
    navigator.geolocation.getCurrentPosition(
        async (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            currentCoords = [lat, lng];
            
            // Удаляем предыдущий временный маркер
            if (tempMarker) {
                map.removeLayer(tempMarker);
            }
            
            // Создаем маркер
            const color = formType === 'task' ? 'red' : 'green';
            const icon = L.divIcon({
                className: 'custom-marker',
                html: `<div style="width:18px;height:18px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.5);"></div>`,
                iconSize: [18, 18],
                iconAnchor: [9, 9]
            });
            
            tempMarker = L.marker([lat, lng], { icon, draggable: true }).addTo(map);
            
            // Центрируем карту
            map.setView([lat, lng], 15);
            
            // Получаем адрес по координатам
            hint.textContent = 'Получение адреса...';
            const address = await getAddressFromCoords(lat, lng);
            const addressText = address || `Минск, координаты: ${lat.toFixed(6)}, ${lng.toFixed(6)}`;
            
            // Обновляем адрес (пользователь может отредактировать)
            if (formType === 'task') {
                document.getElementById('taskAddress').value = addressText;
            } else {
                document.getElementById('workerAddress').value = addressText;
            }
            
            // Перемещение маркера
            tempMarker.on('dragend', async () => {
                const newLatLng = tempMarker.getLatLng();
                currentCoords = [newLatLng.lat, newLatLng.lng];
                
                // Обновляем адрес при перемещении
                const newAddress = await getAddressFromCoords(newLatLng.lat, newLatLng.lng);
                const newAddressText = newAddress || `Минск, координаты: ${newLatLng.lat.toFixed(6)}, ${newLatLng.lng.toFixed(6)}`;
                
                if (formType === 'task') {
                    document.getElementById('taskAddress').value = newAddressText;
                } else {
                    document.getElementById('workerAddress').value = newAddressText;
                }
            });
            
            hideHint();
        },
        (error) => {
            hideHint();
            let errorMessage = 'Не удалось получить геолокацию';
            
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    errorMessage = 'Доступ к геолокации запрещён. Разрешите доступ в настройках браузера.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    errorMessage = 'Информация о местоположении недоступна.';
                    break;
                case error.TIMEOUT:
                    errorMessage = 'Время ожидания геолокации истекло.';
                    break;
            }
            
            alert(errorMessage);
            console.error('Ошибка геолокации:', error);
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }
    );
}

// Выбор места на карте
function selectOnMap(formType) {
    currentMode = formType;
    showHint('Нажмите на карте, где будет работа');
    // Закрываем модальное окно временно, чтобы пользователь мог кликнуть на карте
    if (formType === 'task') {
        document.getElementById('taskModal').classList.remove('active');
    } else {
        document.getElementById('workerModal').classList.remove('active');
    }
}

// Отправка задачи
async function submitTask(event) {
    event.preventDefault();
    
    if (!currentCoords) {
        alert('Выберите место на карте или используйте геолокацию');
        return;
    }
    
    const amount = document.getElementById('taskPaymentAmount').value;
    const type = document.getElementById('taskPaymentType').value;
    const payment = type === 'договорная' ? 'Договорная' : `${amount} ${type}`;
    
    const data = {
        type: 'task',
        title: document.getElementById('taskTitle').value,
        description: document.getElementById('taskDescription').value,
        address: document.getElementById('taskAddress').value,
        payment: payment,
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
        alert('Выберите место на карте или используйте геолокацию');
        return;
    }
    
    const amount = document.getElementById('workerPaymentAmount').value;
    const type = document.getElementById('workerPaymentType').value;
    const payment = type === 'договорная' ? 'Договорная' : `от ${amount} ${type}`;
    
    const data = {
        type: 'worker',
        title: document.getElementById('workerTitle').value,
        description: document.getElementById('workerDescription').value,
        address: document.getElementById('workerAddress').value,
        payment: payment,
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
        
        // Сохраняем объявления для карты и перерисовываем маркеры с учётом фильтра
        mapListings = listings || [];
        renderMapMarkers();
    } catch (error) {
        console.error('Ошибка загрузки объявлений:', error);
    }
}

// Перерисовка маркеров на карте с учётом текущего фильтра
function renderMapMarkers() {
    if (!map) return;

    // Удаляем старые маркеры
    markers.forEach(marker => {
        map.removeLayer(marker);
    });
    markers = [];

    const filtered = mapListings.filter(listing => {
        if (currentMapFilter === 'task') return listing.type === 'task';
        if (currentMapFilter === 'worker') return listing.type === 'worker';
        return true; // all
    });

    filtered.forEach(listing => {
        const color = listing.type === 'task' ? 'red' : 'green';
        const icon = L.divIcon({
            className: 'custom-marker',
            html: `<div style="width:18px;height:18px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.5);"></div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });

        const popupContent = `
            <div class="job-popup-content">
                <strong>${listing.title}</strong><br>
                <small>${listing.address}</small><br>
                <strong>💰 ${listing.payment}</strong><br>
                <button onclick="window.showListingDetail(${listing.id})" class="job-popup-button">
                    Подробнее
                </button>
            </div>
        `;

        const marker = L.marker([listing.latitude, listing.longitude], { 
            icon
        });
        
        // Сохраняем ID объявления в маркере
        marker._listingId = listing.id;
        
        marker.bindPopup(popupContent, {
            className: 'job-popup',
            maxWidth: 260,
            minWidth: 260,
            autoPan: true
        })
            .on('click', () => showListingDetail(listing.id))
            .addTo(map);

        markers.push(marker);
    });
}

// Показать детали объявления (глобальная функция для popup)
window.showListingDetail = async function(listingId) {
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
};

// Также создаём обычную функцию для совместимости
async function showListingDetail(listingId) {
    return window.showListingDetail(listingId);
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

// Глобальные переменные для доски объявлений
let allListings = [];
let currentBoardTab = 'tasks';

// Показать доску объявлений
async function showBoard() {
    try {
        const response = await fetch('/api/listings');
        allListings = await response.json();
        
        document.getElementById('boardModal').classList.add('active');
        applyFilters();
    } catch (error) {
        console.error('Ошибка загрузки объявлений:', error);
        alert('Не удалось загрузить объявления');
    }
}

// Быстрый фильтр маркеров на карте (полоска фильтров)
function setMapFilter(filter, element) {
    currentMapFilter = filter;

    // Синхронизируем активное состояние: полоска фильтров
    const stripButtons = document.querySelectorAll('.map-filter-button');
    stripButtons.forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });

    renderMapMarkers();
}

// Привязка обработчиков к кнопкам фильтров карты (мобильные: touchstart, десктоп: click)
function initMapFilters() {
    const buttons = document.querySelectorAll('.map-filter-button');
    if (!buttons || buttons.length === 0) {
        return;
    }

    function applyFilter(btn) {
        var filter = btn.dataset.filter || 'all';
        setMapFilter(filter, btn);
    }

    buttons.forEach(function(btn) {
        // На мобильных: перехватываем touchstart в фазе capture, чтобы карта не забирала касание
        btn.addEventListener('touchstart', function(e) {
            e.preventDefault();
            e.stopPropagation();
            applyFilter(btn);
        }, { passive: false, capture: true });
        // Десктоп
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            applyFilter(btn);
        });
    });

}

// Переключение вкладок доски
function switchBoardTab(tab) {
    currentBoardTab = tab;
    document.querySelectorAll('#boardModal .tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    applyFilters();
}

// Применение фильтров
function applyFilters() {
    const searchText = document.getElementById('filterSearch').value.toLowerCase();
    const minPayment = parseFloat(document.getElementById('filterMinPayment').value) || 0;
    const paymentType = document.getElementById('filterPaymentType').value;
    
    let filtered = allListings.filter(listing => {
        // Фильтр по типу
        if (currentBoardTab === 'tasks' && listing.type !== 'task') return false;
        if (currentBoardTab === 'workers' && listing.type !== 'worker') return false;
        
        // Фильтр по поисковому запросу
        if (searchText && !listing.title.toLowerCase().includes(searchText) && 
            !listing.description.toLowerCase().includes(searchText)) {
            return false;
        }
        
        // Фильтр по оплате
        if (minPayment > 0 || paymentType) {
            const payment = listing.payment || '';
            const paymentLower = payment.toLowerCase();
            
            // Извлекаем число из строки оплаты
            const paymentMatch = payment.match(/(\d+\.?\d*)/);
            const paymentAmount = paymentMatch ? parseFloat(paymentMatch[1]) : 0;
            
            if (minPayment > 0 && paymentAmount < minPayment) return false;
            
            if (paymentType && !paymentLower.includes(paymentType.toLowerCase())) return false;
        }
        
        return true;
    });
    
    renderBoardListings(filtered);
}

// Рендер списка объявлений на доске
function renderBoardListings(listings) {
    const container = document.getElementById('boardListings');
    
    if (listings.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Нет объявлений</p>';
        return;
    }
    
    container.innerHTML = listings.map(listing => {
        const typeClass = listing.type === 'task' ? 'task' : 'worker';
        const typeEmoji = listing.type === 'task' ? '🔴' : '🟢';
        const typeText = listing.type === 'task' ? 'Ищут исполнителя' : 'Ищут работу';
        
        return `
            <div class="listing-card" onclick="showListingDetail(${listing.id})">
                <div class="listing-card-header">
                    <span class="listing-card-type ${typeClass}">${typeEmoji} ${typeText}</span>
                </div>
                <div class="listing-card-title">${listing.title}</div>
                <div class="listing-card-info">📍 ${listing.address}</div>
                <div class="listing-card-info">💰 ${listing.payment}</div>
                <div class="listing-card-info" style="margin-top: 8px; color: #999; font-size: 12px;">
                    ${listing.description.substring(0, 100)}${listing.description.length > 100 ? '...' : ''}
                </div>
            </div>
        `;
    }).join('');
}

