import time

from barq import Barq
from barq import Request
from barq import Response
from barq import StreamingResponse
from barq import stream_parallel


app = Barq()


@app.middleware
def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = call_next(request)
    elapsed = time.perf_counter() - start
    if isinstance(response, Response):
        response.headers["x-response-time"] = f"{elapsed:.4f}s"
    return response


@app.middleware
def logging_middleware(request: Request, call_next):
    print(f"--> {request.method} {request.path}")
    response = call_next(request)
    status = response.status_code
    print(f"<-- {request.method} {request.path} [{status}]")
    return response


def slow_task(task_id: int, duration: float) -> dict:
    time.sleep(duration)
    return {"task_id": task_id, "duration": duration, "completed_at": time.time()}


@app.get("/")
def index() -> dict:
    return {"message": "Streaming example", "endpoints": ["/stream", "/parallel", "/sse"]}


@app.get("/stream")
def stream_basic():
    def generate():
        for i in range(5):
            time.sleep(0.5)
            yield {"chunk": i, "timestamp": time.time()}
    return StreamingResponse.json_stream(generate())


@app.get("/parallel")
def stream_parallel_tasks():
    tasks = [
        lambda: slow_task(0, 2.0),
        lambda: slow_task(1, 0.5),
        lambda: slow_task(2, 1.5),
        lambda: slow_task(3, 0.3),
        lambda: slow_task(4, 1.0),
    ]
    return StreamingResponse.json_stream(stream_parallel(tasks, workers=4))


@app.get("/sse")
def server_sent_events():
    def generate():
        for i in range(10):
            time.sleep(0.5)
            yield {
                "event": "update",
                "id": str(i),
                "data": {"counter": i, "timestamp": time.time()},
            }
        yield {"event": "done", "data": "Stream complete"}
    return StreamingResponse.sse(generate())


@app.get("/text-stream")
def text_stream():
    def generate():
        words = "The quick brown fox jumps over the lazy dog".split()
        for word in words:
            time.sleep(0.3)
            yield word + " "
    return StreamingResponse.text_stream(generate())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=4)
