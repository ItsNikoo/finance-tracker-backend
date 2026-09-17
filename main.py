from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette import status

app = FastAPI()


class Transaction(BaseModel):
    amount: int


@app.get("/")
def read_root():
    return {"Hello": "World"}


balance = 0


@app.get("/balance")
def check_balance():
    return {"balance": balance}


@app.post("/balance/income")
def add_income_transaction(transaction: Transaction):
    global balance
    if transaction.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Транзакция дохода должна быть положительной"
        )
    balance += transaction.amount
    return {
        "income": transaction.amount,
        "total_balance": balance
    }


@app.post("/balance/expense")
def add_expense_transaction(transaction: Transaction):
    global balance
    if transaction.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Транзаакция расхода должна быть положительной"
        )
    if transaction.amount > balance:
        raise HTTPException(
            status_code=400,
            detail="Не хватает денежных средств на балансе"
        )
    balance -= transaction.amount
    return {
        "expense": transaction.amount,
        "total_balance": balance
    }