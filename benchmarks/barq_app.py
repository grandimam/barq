import sqlite3
import time

from threading import local
from typing import Annotated

from pydantic import BaseModel

from barq import Barq
from barq import Depends
from barq import Request
from barq import Response
from barq import StreamingResponse
from barq import stream_parallel

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
    result: int
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
    total = 0
    iterations = 100000
    for i in range(iterations):
        total += i * i
    return CpuResponse(result=total, iterations=iterations)


class StreamItem(BaseModel):
    index: int
    result: int
    completed_at: float


class ParallelResponse(BaseModel):
    results: list[StreamItem]
    total_time: float


def cpu_task(task_id: int) -> dict:
    total = 0
    for i in range(50000):
        total += i * i
    return {"index": task_id, "result": total, "completed_at": time.time()}


@app.get("/parallel")
def parallel_endpoint() -> ParallelResponse:
    start = time.time()
    tasks = [lambda i=i: cpu_task(i) for i in range(4)]
    results = list(stream_parallel(tasks, workers=4))
    items = [StreamItem(**r["result"]) for r in results]
    return ParallelResponse(results=items, total_time=time.time() - start)


@app.get("/stream")
def stream_endpoint():
    tasks = [lambda i=i: cpu_task(i) for i in range(4)]
    return StreamingResponse.json_stream(stream_parallel(tasks, workers=4))


@app.middleware
def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = call_next(request)
    elapsed = time.perf_counter() - start
    if isinstance(response, Response):
        response.headers["x-response-time"] = f"{elapsed:.6f}"
    return response


@app.on_startup
def startup() -> None:
    init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, workers=4)
