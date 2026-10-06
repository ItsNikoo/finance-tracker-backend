from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.docs import swagger_docs
from app.dependencies.auth import require_csrf
from app.settings import get_allowed_origins

from app.v1.user_router import router as user_router
from app.v1.transaction_router import router as transaction_router
from app.v1.category_router import router as category_router

app = FastAPI(docs_url=None, dependencies=[Depends(require_csrf)])
app.add_api_route("/docs", swagger_docs, methods=["GET"], include_in_schema=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


# Запрещает кеширование ответов API с данными пользователя.
@app.middleware("http")
async def disable_api_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def read_root():
    return {"Hello": "World"}


balance = 0

app.include_router(transaction_router, prefix="/api")
app.include_router(category_router, prefix="/api")
app.include_router(user_router, prefix="/api")
