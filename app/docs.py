import json

from fastapi import Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse


# Swagger получает актуальный CSRF перед каждым изменяющим запросом.
CSRF_INTERCEPTOR = """
async function swaggerCsrfInterceptor(request) {
    const target = new URL(request.url, window.location.href);
    if (target.origin !== window.location.origin) return request;
    request.credentials = "include";
    const method = (request.method || "GET").toUpperCase();
    if (["GET", "HEAD", "OPTIONS"].includes(method)) return request;
    const response = await fetch(csrfUrl, {
        credentials: "include", cache: "no-store"
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Не удалось получить CSRF-токен");
    }
    const data = await response.json();
    if (!data.csrf_token) throw new Error("Сервер не вернул CSRF-токен");
    request.headers = request.headers || {};
    for (const name of Object.keys(request.headers)) {
        if (name.toLowerCase() === "x-csrf-token") delete request.headers[name];
    }
    request.headers["X-CSRF-Token"] = data.csrf_token;
    return request;
}
"""


AUTH_CLIENT = """
async function swaggerAuthRequest(url, body) {
    const request = await swaggerCsrfInterceptor({
        url, method: "POST", headers: {"Content-Type": "application/json"}
    });
    const response = await fetch(url, {
        method: request.method, headers: request.headers,
        credentials: "include", cache: "no-store",
        ...(body === undefined ? {} : {body: JSON.stringify(body)})
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const detail = Array.isArray(data.detail)
            ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || `Ошибка входа/выхода (${response.status})`);
    }
    return response.status === 204 ? null : response.json();
}
"""


AUTH_DIALOG = """
<style>
#swagger-login {border:0;border-radius:12px;padding:28px;width:360px;max-width:90vw;
    box-shadow:0 12px 50px #0004;font:15px sans-serif;color:#263238}
#swagger-login::backdrop {background:#0006}
#swagger-login h2 {margin-top:0}
#swagger-login label {display:block;margin:14px 0 6px}
#swagger-login input {box-sizing:border-box;width:100%;padding:10px;border:1px solid #aaa;border-radius:4px}
#swagger-login button {padding:9px 14px;margin:14px 6px 0 0;cursor:pointer}
#swagger-auth-error {color:#b71c1c}
#swagger-auth-status {overflow-wrap:anywhere}
</style>
<dialog id="swagger-login" aria-labelledby="swagger-login-title">
    <h2 id="swagger-login-title">Вход в API</h2>
    <p id="swagger-auth-status" role="status"></p>
    <form id="swagger-login-form">
        <label for="swagger-email">Логин (email)</label>
        <input id="swagger-email" name="email" type="email" autocomplete="username" required>
        <label for="swagger-password">Пароль</label>
        <input id="swagger-password" name="password" type="password" autocomplete="current-password" required>
        <button id="swagger-login-submit" type="submit">Войти</button>
    </form>
    <p id="swagger-auth-error" role="alert"></p>
    <button id="swagger-logout" type="button" hidden>Выйти</button>
    <button id="swagger-auth-close" type="button">Закрыть</button>
</dialog>
"""


AUTH_DIALOG_SCRIPT = """
(() => {
    const dialog = document.getElementById("swagger-login");
    const form = document.getElementById("swagger-login-form");
    const email = document.getElementById("swagger-email");
    const password = document.getElementById("swagger-password");
    const submit = document.getElementById("swagger-login-submit");
    const logout = document.getElementById("swagger-logout");
    const error = document.getElementById("swagger-auth-error");
    const status = document.getElementById("swagger-auth-status");
    let user = null;
    function render() {
        status.textContent = user ? `Вы вошли: ${user.email}` : "Введите email и пароль своего аккаунта.";
        form.hidden = !!user;
        logout.hidden = !user;
    }
    async function refreshUser() {
        try {
            const response = await fetch(authUrls.me, {credentials: "include", cache: "no-store"});
            if (response.ok) user = await response.json();
            else if (response.status === 401) user = null;
            else throw new Error(`Не удалось проверить сессию (${response.status})`);
            render();
        } catch (failure) {error.textContent = failure.message;}
    }
    document.addEventListener("click", async event => {
        if (!event.target.closest(".auth-wrapper .authorize, .authorization__btn")) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        error.textContent = "";
        password.value = "";
        render();
        if (!dialog.open) dialog.showModal();
        submit.disabled = true;
        await refreshUser();
        submit.disabled = false;
    }, true);
    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (submit.disabled) return;
        submit.disabled = true;
        error.textContent = "";
        try {
            const result = await swaggerAuthRequest(authUrls.login, {email: email.value, password: password.value});
            user = result.user;
            form.reset();
            render();
        } catch (failure) {error.textContent = failure.message;}
        finally {password.value = ""; submit.disabled = false;}
    });
    logout.addEventListener("click", async () => {
        logout.disabled = true;
        error.textContent = "";
        try {
            await swaggerAuthRequest(authUrls.logout);
            user = null;
            form.reset();
            render();
        } catch (failure) {error.textContent = failure.message;}
        finally {logout.disabled = false;}
    });
    document.getElementById("swagger-auth-close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {password.value = ""; error.textContent = "";});
    render();
})();
"""


def swagger_docs(request: Request) -> HTMLResponse:
    root_path = request.scope.get("root_path", "").rstrip("/")
    response = get_swagger_ui_html(
        openapi_url=f"{root_path}{request.app.openapi_url}",
        title=f"{request.app.title} - Swagger UI",
        swagger_ui_parameters={"withCredentials": True},
    )
    csrf_url = json.dumps(f"{root_path}/api/users/csrf").replace("<", "\\u003c")
    auth_urls = json.dumps({
        "login": f"{root_path}/api/users/login",
        "logout": f"{root_path}/api/users/logout",
        "me": f"{root_path}/api/users/me",
    }).replace("<", "\\u003c")
    html = response.body.decode().replace(
        "const ui = SwaggerUIBundle({",
        f"const csrfUrl = {csrf_url};\nconst authUrls = {auth_urls};\n{CSRF_INTERCEPTOR}\n{AUTH_CLIENT}\n"
        "const ui = SwaggerUIBundle({\nrequestInterceptor: swaggerCsrfInterceptor,",
        1,
    )
    html = html.replace("</body>", f"{AUTH_DIALOG}<script>{AUTH_DIALOG_SCRIPT}</script></body>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
