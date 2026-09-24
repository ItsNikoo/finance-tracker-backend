from fastapi import FastAPI

from app.v1.user_router import router as user_router
from app.v1.transaction_router import router as transaction_router
from app.v1.category_router import router as category_router

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


balance = 0

app.include_router(transaction_router, prefix="/api")
app.include_router(category_router, prefix="/api")
app.include_router(user_router, prefix="/api")
