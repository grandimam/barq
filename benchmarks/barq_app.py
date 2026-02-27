import sqlite3

from threading import local
from typing import Annotated

import blake3
from pydantic import BaseModel

from barq import Barq
from barq import Depends

app = Barq()

DB_PATH = "/tmp/barq_bench.db"
_thread_local = local()


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
    if not hasattr(_thread_local, "conn"):
        _thread_local.conn = sqlite3.connect(DB_PATH)
        _thread_local.conn.row_factory = sqlite3.Row
    return _thread_local.conn


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


@app.on_startup
def startup() -> None:
    init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, workers=4)
