import time
import hashlib
import cProfile
import pstats
from io import StringIO

from pydantic import BaseModel
from barq import Barq, Response
from barq.request import Request
from barq.routing import Router


class CpuResponse(BaseModel):
    hash: str
    iterations: int


def cpu_work() -> CpuResponse:
    data = b"benchmark data for hashing"
    result = data
    for _ in range(5000):
        result = hashlib.sha256(result).digest()
    return CpuResponse(hash=result.hex(), iterations=5000)


def measure(label: str, fn, iterations: int = 100):
    # Warmup
    for _ in range(10):
        fn()

    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / iterations) * 1000
    print(f"{label}: {avg_ms:.3f} ms/call")


def main():
    print("=" * 60)
    print("PROFILING CPU-BOUND REQUEST COMPONENTS")
    print("=" * 60)
    print()

    # 1. Pure CPU work (SHA256)
    print("1. Pure CPU Work (SHA256 x 5000)")
    measure("   SHA256 hashing", lambda: hashlib.sha256(b"x" * 1000).digest() and [hashlib.sha256(b"test").digest() for _ in range(5000)])
    print()

    # 2. Pydantic model creation
    print("2. Pydantic Model Creation")
    measure("   CpuResponse()", lambda: CpuResponse(hash="a" * 64, iterations=5000))
    print()

    # 3. Pydantic JSON serialization
    print("3. Pydantic JSON Serialization")
    model = CpuResponse(hash="a" * 64, iterations=5000)
    measure("   model.model_dump_json()", lambda: model.model_dump_json())
    print()

    # 4. Response.json() creation
    print("4. Response.json() Creation")
    measure("   Response.json(model)", lambda: Response.json(model))
    print()

    # 5. Request object creation
    print("5. Request Object Creation")
    measure("   Request(...)", lambda: Request(
        method="GET",
        path="/cpu",
        headers={"content-type": "application/json"},
        query_string="",
        body=b"",
    ))
    print()

    # 6. Router matching
    print("6. Router Matching")
    router = Router()
    router.add("/cpu", "GET", lambda r, p: None)
    router.add("/json", "GET", lambda r, p: None)
    router.add("/items/{id}", "GET", lambda r, p: None)
    measure("   router.match('/cpu', 'GET')", lambda: router.match("/cpu", "GET"))
    print()

    # 7. Full handler (without network)
    print("7. Full Handler Simulation")
    app = Barq()

    @app.get("/cpu")
    def cpu_endpoint() -> CpuResponse:
        return cpu_work()

    fake_request = Request(
        method="GET",
        path="/cpu",
        headers={},
        query_string="",
        body=b"",
    )

    def simulate_full():
        return app._handle(fake_request)

    measure("   Full _handle() call", simulate_full, iterations=50)
    print()

    # 8. Breakdown
    print("=" * 60)
    print("BREAKDOWN")
    print("=" * 60)

    # Profile full handler
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(50):
        app._handle(fake_request)
    pr.disable()

    s = StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())


if __name__ == "__main__":
    main()
