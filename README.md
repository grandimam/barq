# Barq

> **⚠️ Experimental**: This project is a proof-of-concept exploring free-threaded Python (PEP 703) for HTTP frameworks. Not production-ready.

A pure-Python HTTP framework built for free-threaded Python 3.13+. No C extensions, no async/await just threads with true parallelism.

## Requirements

- Python 3.13+ with free-threading enabled (`python3.13t`)
- [uv](https://github.com/astral-sh/uv) package manager

## Installation

```bash
uv add barq
```

## Development Setup

```bash
git clone https://github.com/grandimam/barq.git
cd barq

# Install
uv sync

# Run
uv run python examples/basic.py

# Test
curl http://localhost:8000/
curl http://localhost:8000/items/1
curl -X POST http://localhost:8000/items -H "Content-Type: application/json" -d '{"name":"Widget","price":9.99}'
```

## Running Benchmarks

```bash
# Install dev dependencies
uv sync --dev

# Run benchmark
uv run python benchmarks/run_benchmark.py 1000 10
```

## Quick Start

```python
from typing import Annotated
from pydantic import BaseModel
from barq import Barq, Depends

app = Barq()

class Item(BaseModel):
    name: str
    price: float

@app.get("/")
def index() -> dict:
    return {"message": "Hello, World!"}

@app.get("/items/{item_id}")
def get_item(item_id: int) -> dict:
    return {"id": item_id}

@app.post("/items")
def create_item(body: Item) -> Item:
    return body

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=4)
```

## Features

- **Pure Python**: No C extensions, no Rust, no Cython
- **Free-threaded**: True parallelism without the GIL (Python 3.13t)
- **Type-driven**: Pydantic models auto-parsed from request body
- **Dependency injection**: `Depends()` with request-scoped caching
- **Minimal**: ~465 lines of code in 4 files

## Benchmarks

Comparison against FastAPI (uvicorn, 4 worker processes).

### System

| Component | Value                  |
| --------- | ---------------------- |
| CPU       | Apple M2 Pro           |
| Cores     | 12                     |
| Python    | 3.13.0 (free-threaded) |
| Platform  | Darwin arm64           |

### Results (1000 requests, 10 concurrent clients)

| Scenario      | Barq (4 threads) | FastAPI (4 processes) | Difference               |
| ------------- | ---------------- | --------------------- | ------------------------ |
| **JSON**      | 10,114 req/s     | 5,665 req/s           | **Free Threaded: +79%**  |
| **DB Query**  | 9,962 req/s      | 1,015 req/s           | **Free Threaded: +881%** |
| **CPU Bound** | 879 req/s        | 1,231 req/s           | FastAPI: +29%            |

### Analysis

- **JSON/DB (I/O bound)**: Barq wins due to shared memory, no IPC overhead
- **CPU bound**: FastAPI wins due to process isolation (no memory contention)

Note: CPU benchmark uses pure Python arithmetic. C extensions like `hashlib` have internal locks that prevent parallelism even with free-threaded Python.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Barq App                         │
│              (app.py: routing, DI, handlers)            │
├─────────────────────────────────────────────────────────┤
│                    Request / Response                   │
│               (types.py: dataclasses)                   │
├─────────────────────────────────────────────────────────┤
│                      HTTP Parser                        │
│            (http.py: parse/write HTTP/1.1)              │
├─────────────────────────────────────────────────────────┤
│                   ThreadPoolExecutor                    │
│              (server.py: socket handling)               │
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
src/barq/
├── __init__.py   # exports
├── app.py        # Barq, Depends, Router
├── types.py      # Request, Response, HTTPException
├── server.py     # Server, ThreadPool, SocketReader
└── http.py       # HTTPParser, write_response
```

## Why Free-Threaded Python?

Traditional Python has the GIL (Global Interpreter Lock), which prevents true parallelism in threads. Web frameworks work around this using:

- **Async/await** (FastAPI, Starlette): Cooperative multitasking
- **Multiprocessing** (Gunicorn, uvicorn): Separate processes with IPC overhead

Free-threaded Python (PEP 703) removes the GIL, enabling:

- **Simple synchronous code** that runs in parallel
- **Shared memory** between threads (no serialization)
- **Lower overhead** than multiprocessing

## Limitations

- Experimental—not battle-tested
- HTTP/1.1 only (no HTTP/2, no WebSocket)
- No middleware system (yet)
- C extensions with internal locks don't parallelize

## License

MIT
