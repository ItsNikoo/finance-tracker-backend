# Подключение frontend к cookie-аутентификации

## Локальный запуск

Frontend: `http://localhost:5173`. Backend: `http://localhost:8000`.
Используйте `localhost` с обеих сторон, не смешивайте его с `127.0.0.1`.

Swagger доступен по `http://localhost:8000/docs`: перед каждым изменяющим
запросом он автоматически получает CSRF-токен и отправляет его вместе с cookies.
Для входа выполните `POST /api/users/login` через **Try it out**, затем можно
вызывать `/api/users/me` и остальные защищённые методы в той же вкладке.
Адрес Swagger должен входить в `ALLOWED_ORIGINS` (локальный адрес выше уже включён).

Настройки в корневом `.env` (существующий секрет не менять):

```dotenv
JWT_SECRET_KEY=<ваш текущий случайный секрет>
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000
COOKIE_SECURE=false
```

Адреса и `COOKIE_SECURE=false` выше являются локальными значениями по умолчанию.
При изменении `.env` перезапустите backend. На HTTPS-сервере задайте
`COOKIE_SECURE=true` и перечислите реальные доверенные origins вместо локальных.
Предпочтительное размещение в production: сайт и `/api` на одном origin.
Схема использует `SameSite=Lax`; frontend и API на разных сайтах этим вариантом не поддерживаются.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

## Контракт API

Все адреса ниже имеют префикс `/api`. Во всех fetch указывайте `credentials: "include"`.
Не передавайте `Authorization`, не читайте cookies через JS и не сохраняйте access/refresh в localStorage.
Старый Bearer-формат больше не используется: после обновления backend войдите заново.

| Метод и путь | Тело запроса | Результат |
|---|---|---|
| `GET /users/csrf` | Нет | `200 {"csrf_token": "..."}` и CSRF-cookie |
| `POST /users/create` | `{email, password}` | `201 {id, email, created_at}`; без автоматического входа |
| `POST /users/login` | `{email, password}` | `200 {user: {id, email, created_at}, csrf_token}` и три cookies |
| `GET /users/me` | Нет | `200 {id, email, created_at}` или `401` |
| `POST /users/refresh` | Нет | `200 {user, csrf_token}` и новая пара access/refresh cookies |
| `POST /users/logout` | Нет | `204`, отзыв текущей сессии и удаление cookies |

`POST`, `PUT`, `PATCH`, `DELETE` требуют заголовка `X-CSRF-Token` и доверенного `Origin`.
Это относится также к регистрации, входу и созданию категорий. `Origin` браузер выставляет сам;
из JavaScript вручную его задавать не нужно. Для curl/Postman указывайте доверенный Origin явно.
CSRF-токен берите из JSON ответа `/users/csrf` и держите в памяти приложения.

## Сценарии клиента

1. При открытии приложения запросите `/users/csrf`, затем `/users/me`.
2. Если `/me` вернул `401`, один раз вызовите `/users/refresh` и повторите `/me`.
   Если refresh тоже вернул `401`, покажите форму входа: пользователь не авторизован.
3. Регистрация: отправьте `/users/create`, затем выполните обычный вход.
4. Вход: отправьте `/users/login`, запомните `user` и **новый** `csrf_token` из JSON.
   Браузер сам сохранит HttpOnly cookies. Перейдите к транзакциям.
5. При `401` защищённого запроса обновите сессию один раз и повторите исходный запрос один раз.
   Не запускайте refresh для неудачного логина или самого refresh.
6. При `403` с сообщением о CSRF заново получите `/users/csrf` и повторите запрос один раз.
   Это необходимо, например, после входа/выхода в другой вкладке или истечения сессии.
   Не повторяйте автоматически остальные `403`, например запрет Origin.
7. Выход: вызовите `/users/logout`, дождитесь `204`, очистите профиль, CSRF в памяти
   и весь кеш пользовательских данных (включая React Query/SWR). Перейдите на вход.
   Если сеть недоступна, не считайте серверную сессию отозванной: покажите ошибку и возможность повторить.

При `409` на регистрации покажите, что email занят. При `422` отобразите ошибки полей.
Не превращайте сетевые ошибки и `500` в состояние «не авторизован».

## Пример общего клиента JavaScript

Код рассчитан на JSON-запросы. Его можно положить в будущий frontend как `src/api/client.js`.
CSRF хранится только в памяти; access/refresh доступны только браузеру.

```javascript
const API = "http://localhost:8000/api";
let csrfToken = null;
let csrfPromise = null;
let refreshPromise = null;

async function loadCsrf() {
  if (!csrfPromise) {
    csrfPromise = fetch(`${API}/users/csrf`, {
      credentials: "include",
      cache: "no-store",
    }).then(async (response) => {
      if (!response.ok) throw new Error("Не удалось получить CSRF-токен");
      csrfToken = (await response.json()).csrf_token;
      return csrfToken;
    }).finally(() => { csrfPromise = null; });
  }
  return csrfPromise;
}

async function send(path, { method = "GET", body } = {}, retryCsrf = true) {
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
  if (unsafe && !csrfToken) await loadCsrf();
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (unsafe) headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(`${API}${path}`, {
    method, headers, credentials: "include", cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 403 && unsafe && retryCsrf) {
    const error = await response.clone().json().catch(() => ({}));
    if (["Некорректный CSRF-токен", "Обновите CSRF-токен"].includes(error.detail)) {
      await loadCsrf();
      return send(path, { method, body }, false);
    }
  }
  return response;
}

async function refreshSession() {
  if (!refreshPromise) {
    const refresh = async () => {
      // Другая вкладка могла обновить общую cookie, пока мы ждали блокировку.
      const me = await send("/users/me");
      if (me.ok) return;
      if (me.status !== 401) throw new Error("Не удалось проверить сессию");
      const response = await send("/users/refresh", { method: "POST" });
      if (!response.ok) {
        const error = new Error(response.status === 401 ? "Требуется вход" : "Не удалось обновить сессию");
        error.status = response.status;
        throw error;
      }
      csrfToken = (await response.json()).csrf_token;
    };
    // Single flight внутри вкладки; Web Locks — между вкладками одного origin.
    refreshPromise = (navigator.locks
      ? navigator.locks.request("finance-auth", refresh)
      : refresh()
    ).finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

export async function api(path, options = {}) {
  let response = await send(path, options);
  const authEndpoint = ["/users/login", "/users/create", "/users/refresh", "/users/logout", "/users/csrf"].includes(path);
  if (response.status === 401 && !authEndpoint) {
    await refreshSession();
    response = await send(path, options);
  }
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const error = new Error(typeof data?.detail === "string" ? data.detail : "Ошибка запроса");
    error.status = response.status;
    error.details = data;
    throw error;
  }
  if (data?.csrf_token) csrfToken = data.csrf_token;
  if (path === "/users/logout") csrfToken = null;
  return data;
}
```

Использование:

```javascript
await api("/users/csrf");
const user = await api("/users/me"); // при отсутствии сессии обработать error.status === 401
const result = await api("/users/login", {
  method: "POST", body: { email, password },
});
const transactions = await api("/transactions");
await api("/users/logout", { method: "POST" });
```

Для нескольких вкладок синхронизируйте также login/logout через `BroadcastChannel`
(очистка профиля и кеша во всех вкладках), а операции входа/выхода выполняйте под той же
Web Lock `finance-auth`, что и refresh. Web Locks требует безопасный контекст
(HTTPS или localhost). В браузерах без Web Locks нужна аналогичная межвкладочная
координация: проигравший конкурентный refresh получает отказ, не новую пару токенов.

## Поведение сервера

- Access JWT: 15 минут, `sub`, `sid`, `kind=access`, `iat`, `exp`.
- Refresh: случайная строка; БД хранит только SHA-256 хеш.
- Сессия: абсолютные 7 дней. Refresh не продлевает этот срок; затем нужен новый вход.
- При каждом refresh старое значение атомарно заменяется. Повторное использование отвергается.
  Отказ старому refresh сам по себе не отзывает новую сессию.
- Каждый защищённый запрос проверяет состояние сессии в БД, поэтому logout сразу
  запрещает использование ранее скопированного access-токена этой сессии.
- Выход работает и без действующего access, если refresh ещё действителен.
- Выход завершает только текущую сессию; другие устройства остаются авторизованными.
- Все cookies: HttpOnly, SameSite=Lax, Path=/, без Domain; Secure управляется окружением.
- CSRF подписан и привязан к сессии; для входа используется отдельный анонимный CSRF.
- Ответы API имеют Cache-Control: no-store.
- CORS разрешает credentials только перечисленным origins.

Модель прав общих категорий в этой задаче не менялась. Лимиты попыток входа,
восстановление пароля, подтверждение email и управление всеми устройствами — отдельные функции.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Тесты используют изолированные БД, проверяют cookies, CSRF/Origin, login/me,
refresh/logout, срок сессий, конкурентное обновление и изоляцию транзакций.
