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


def swagger_docs(request: Request) -> HTMLResponse:
    root_path = request.scope.get("root_path", "").rstrip("/")
    response = get_swagger_ui_html(
        openapi_url=f"{root_path}{request.app.openapi_url}",
        title=f"{request.app.title} - Swagger UI",
        swagger_ui_parameters={"withCredentials": True},
    )
    csrf_url = json.dumps(f"{root_path}/api/users/csrf").replace("<", "\\u003c")
    html = response.body.decode().replace(
        "const ui = SwaggerUIBundle({",
        f"const csrfUrl = {csrf_url};\n{CSRF_INTERCEPTOR}\n"
        "const ui = SwaggerUIBundle({\nrequestInterceptor: swaggerCsrfInterceptor,",
        1,
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
