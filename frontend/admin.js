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
    console.log("Telegram WebApp недоступен");
}

function setStatus(text) {
    const status = document.getElementById("statusText");
    if (status) {
        status.textContent = text;
    }
}

function apiHeaders(extra = {}) {
    const headers = { ...extra };
    if (isTelegramWebApp && tg && tg.initData) {
        headers["X-Telegram-Init-Data"] = tg.initData;
    }
    return headers;
}

function formatDate(value) {
    if (!value) return "-";
    const dt = new Date(value);
    return dt.toLocaleString("ru-RU");
}

function renderUsers(items) {
    const body = document.getElementById("usersBody");
    if (!body) return;
    if (!items || items.length === 0) {
        body.innerHTML = "<tr><td colspan='7'>Пользователи не найдены</td></tr>";
        return;
    }

    body.innerHTML = items
        .map((user) => {
            const roleClass = user.role === "admin" ? "admin" : "user";
            const banLabel = user.is_banned
                ? `<span class="pill banned">banned</span><div>${user.ban_reason || ""}</div>`
                : "нет";
            const terms = user.accepted_terms_version
                ? `${user.accepted_terms_version}<br><small>${formatDate(user.accepted_terms_at)}</small>`
                : "не приняты";
            const roleSelect = `
                <select onchange="updateRole(${user.id}, this.value)">
                    <option value="user" ${user.role === "user" ? "selected" : ""}>user</option>
                    <option value="admin" ${user.role === "admin" ? "selected" : ""}>admin</option>
                </select>
            `;
            const actionButton = user.is_banned
                ? `<button class="secondary" onclick="unbanUser(${user.id})">Разбан</button>`
                : `<button class="warn" onclick="banUser(${user.id})">Бан</button>`;

            return `
                <tr>
                    <td>${user.id}</td>
                    <td>${user.telegram_id}</td>
                    <td>${user.username || "-"}</td>
                    <td><span class="pill ${roleClass}">${user.role}</span><div style="margin-top:6px;">${roleSelect}</div></td>
                    <td>${banLabel}</td>
                    <td>${terms}</td>
                    <td>${actionButton}</td>
                </tr>
            `;
        })
        .join("");
}

async function loadUsers() {
    try {
        setStatus("Загрузка пользователей...");
        const search = document.getElementById("searchInput")?.value?.trim() || "";
        const role = document.getElementById("roleFilter")?.value || "";
        const isBanned = document.getElementById("banFilter")?.value || "";

        const params = new URLSearchParams();
        if (search) params.set("search", search);
        if (role) params.set("role", role);
        if (isBanned) params.set("is_banned", isBanned);
        params.set("page", "1");
        params.set("page_size", "100");

        const response = await fetch(`/api/admin/users?${params.toString()}`, {
            headers: apiHeaders(),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail?.message || payload.detail || "Ошибка загрузки пользователей");
        }
        renderUsers(payload.items || []);
        setStatus(`Пользователей: ${payload.total || 0}`);
    } catch (error) {
        console.error(error);
        setStatus("Ошибка загрузки пользователей");
        alert(error.message || "Ошибка загрузки пользователей");
    }
}

async function banUser(userId) {
    const reason = prompt("Причина блокировки:", "") || "";
    try {
        const response = await fetch(`/api/admin/users/${userId}/ban`, {
            method: "POST",
            headers: apiHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ reason }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail?.message || payload.detail || "Не удалось заблокировать");
        }
        await Promise.all([loadUsers(), loadAudit()]);
    } catch (error) {
        alert(error.message || "Ошибка при блокировке");
    }
}

async function unbanUser(userId) {
    try {
        const response = await fetch(`/api/admin/users/${userId}/unban`, {
            method: "POST",
            headers: apiHeaders(),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail?.message || payload.detail || "Не удалось снять блокировку");
        }
        await Promise.all([loadUsers(), loadAudit()]);
    } catch (error) {
        alert(error.message || "Ошибка при разбане");
    }
}

async function updateRole(userId, role) {
    try {
        const response = await fetch(`/api/admin/users/${userId}/role`, {
            method: "POST",
            headers: apiHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ role }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail?.message || payload.detail || "Не удалось изменить роль");
        }
        await Promise.all([loadUsers(), loadAudit()]);
    } catch (error) {
        alert(error.message || "Ошибка изменения роли");
        await loadUsers();
    }
}

async function loadAudit() {
    try {
        const response = await fetch("/api/admin/audit?limit=100", {
            headers: apiHeaders(),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail?.message || payload.detail || "Не удалось загрузить аудит");
        }
        const box = document.getElementById("auditBox");
        if (!box) return;
        if (!payload.length) {
            box.textContent = "Журнал пуст";
            return;
        }
        box.innerHTML = payload
            .map((row) => {
                return `<div style="padding:6px 0;border-bottom:1px solid #e5e7eb;">
                    <strong>${row.action}</strong>
                    <div>admin=${row.admin_user_id}, target=${row.target_user_id || "-"}</div>
                    <div>${row.details || "-"}</div>
                    <small>${formatDate(row.created_at)}</small>
                </div>`;
            })
            .join("");
    } catch (error) {
        console.error(error);
        const box = document.getElementById("auditBox");
        if (box) box.textContent = "Ошибка загрузки журнала";
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    await loadUsers();
    await loadAudit();
});
