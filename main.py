from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.v1.transaction_router import router as transaction_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"Hello": "World"}


balance = 0

app.include_router(transaction_router)
