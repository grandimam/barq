import sqlite3

from contextvars import ContextVar
from typing import Annotated

import blake3
from fastapi import Depends
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

DB_PATH = "/tmp/fastapi_bench.db"
_db_conn: ContextVar[sqlite3.Connection | None] = ContextVar("db_conn", default=None)


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


def get_db() -> sqlite3.Connection:
    conn = _db_conn.get()
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _db_conn.set(conn)
    return conn


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class JsonResponse(BaseModel):
    message: str
    items: list[dict[str, int]]
    nested: dict[str, dict[str, str]]


class CpuResponse(BaseModel):
    hash: str
    iterations: int


@app.get("/json")
def json_endpoint() -> JsonResponse:
    return JsonResponse(
        message="Hello, World!",
        items=[{"id": i, "value": i * 10} for i in range(20)],
        nested={
            "level1": {"level2": "deep value"},
            "another": {"key": "value"},
        },
    )


@app.get("/db")
def db_endpoint(db: Annotated[sqlite3.Connection, Depends(get_db)]) -> list[UserResponse]:
    cursor = db.execute("SELECT id, name, email FROM users LIMIT 10")
    rows = cursor.fetchall()
    return [UserResponse(id=row["id"], name=row["name"], email=row["email"]) for row in rows]


@app.get("/cpu")
def cpu_endpoint() -> CpuResponse:
    iterations = 50
    data = b"x" * (1024 * 1024)
    result = ""
    for _ in range(iterations):
        result = blake3.blake3(data).hexdigest()
    return CpuResponse(hash=result, iterations=iterations)


@app.on_event("startup")
def startup() -> None:
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002, workers=4)
