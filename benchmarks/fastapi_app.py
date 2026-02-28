import sqlite3

import aiosqlite
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

DB_PATH = "/tmp/fastapi_bench.db"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)
    conn.execute("DELETE FROM users")
    for i in range(100):
        conn.execute(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            (f"User {i}", f"user{i}@example.com"),
        )
    conn.commit()
    conn.close()


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class JsonResponse(BaseModel):
    message: str
    items: list[dict[str, int]]
    nested: dict[str, dict[str, str]]


class CpuResponse(BaseModel):
    result: int
    iterations: int


@app.get("/json")
async def json_endpoint() -> JsonResponse:
    return JsonResponse(
        message="Hello, World!",
        items=[{"id": i, "value": i * 10} for i in range(20)],
        nested={
            "level1": {"level2": "deep value"},
            "another": {"key": "value"},
        },
    )


@app.get("/db")
async def db_endpoint() -> list[UserResponse]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name, email FROM users LIMIT 10") as cursor:
            rows = await cursor.fetchall()
            return [UserResponse(id=row["id"], name=row["name"], email=row["email"]) for row in rows]


@app.get("/cpu")
async def cpu_endpoint() -> CpuResponse:
    total = 0
    iterations = 100000
    for i in range(iterations):
        total += i * i
    return CpuResponse(result=total, iterations=iterations)


@app.on_event("startup")
def startup() -> None:
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
