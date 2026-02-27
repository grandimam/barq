import statistics
import subprocess
import sys
import time
import urllib.request

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass
class Result:
    name: str
    total: int
    success: int
    failed: int
    total_time: float
    latencies: list[float]

    @property
    def rps(self) -> float:
        return self.success / self.total_time if self.total_time > 0 else 0

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.latencies) * 1000 if self.latencies else 0

    @property
    def p50_ms(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[len(s) // 2] * 1000

    @property
    def p99_ms(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[int(len(s) * 0.99)] * 1000


def bench(name: str, url: str, n: int = 1000, workers: int = 10) -> Result:
    latencies: list[float] = []
    success = 0
    failed = 0

    def request(_: int) -> float | None:
        try:
            start = time.perf_counter()
            with urllib.request.urlopen(url, timeout=10) as resp:
                resp.read()
            return time.perf_counter() - start
        except Exception:
            return None

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(request, range(n)):
            if result is not None:
                latencies.append(result)
                success += 1
            else:
                failed += 1
    total_time = time.perf_counter() - t0

    return Result(name, n, success, failed, total_time, latencies)


def print_result(r: Result) -> None:
    print(f"  {r.name}")
    print(f"    {r.success}/{r.total} ok, {r.rps:.1f} req/s")
    print(f"    latency: avg={r.avg_ms:.1f}ms p50={r.p50_ms:.1f}ms p99={r.p99_ms:.1f}ms")


def wait_server(url: str, timeout: int = 5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    print(f"\n{'='*60}")
    print(f"  BARQ vs FASTAPI  ({n} requests, {workers} workers)")
    print(f"{'='*60}\n")

    procs: list[subprocess.Popen] = []
    try:
        print("Starting servers...")
        procs.append(subprocess.Popen(
            [sys.executable, "benchmarks/barq_app.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ))
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "benchmarks.fastapi_app:app",
             "--host", "127.0.0.1", "--port", "8002", "--workers", "4"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ))

        if not wait_server("http://127.0.0.1:8001/json"):
            print("Barq failed to start")
            return
        if not wait_server("http://127.0.0.1:8002/json"):
            print("FastAPI failed to start")
            return

        print("Servers ready.\n")
        time.sleep(0.5)

        tests = [
            ("JSON", "/json"),
            ("DB", "/db"),
            ("CPU", "/cpu"),
        ]

        for label, path in tests:
            print(f"─── {label} ───")
            barq = bench("Barq", f"http://127.0.0.1:8001{path}", n, workers)
            fapi = bench("FastAPI", f"http://127.0.0.1:8002{path}", n, workers)
            print_result(barq)
            print_result(fapi)

            diff = ((barq.rps / fapi.rps) - 1) * 100 if fapi.rps > 0 else 0
            winner = "Barq" if diff > 0 else "FastAPI"
            print(f"    → {winner} {abs(diff):.1f}% faster\n")

    finally:
        for p in procs:
            p.terminate()
            p.wait()

    print("Done.")


if __name__ == "__main__":
    main()
