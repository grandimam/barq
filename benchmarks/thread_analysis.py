import time
import threading
import hashlib
from concurrent.futures import ThreadPoolExecutor
import urllib.request


def test_thread_parallelism():
    """Test if threads actually run in parallel with CPU work"""
    print("=" * 60)
    print("THREAD PARALLELISM TEST")
    print("=" * 60)

    def cpu_work(thread_id: int) -> float:
        start = time.perf_counter()
        data = b"test"
        for _ in range(5000):
            data = hashlib.sha256(data).digest()
        elapsed = time.perf_counter() - start
        return elapsed

    # Single thread
    print("\n1. Single thread (baseline):")
    t0 = time.perf_counter()
    for i in range(4):
        cpu_work(0)
    single_time = time.perf_counter() - t0
    print(f"   4 tasks sequential: {single_time:.3f}s")

    # 4 threads
    print("\n2. Four threads (should be ~4x faster if parallel):")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(cpu_work, range(4)))
    parallel_time = time.perf_counter() - t0
    print(f"   4 tasks parallel:   {parallel_time:.3f}s")
    print(f"   Speedup: {single_time / parallel_time:.2f}x")

    if parallel_time < single_time * 0.5:
        print("   ✓ TRUE PARALLELISM (free-threaded Python working!)")
    else:
        print("   ✗ NO PARALLELISM (GIL still active?)")


def test_server_concurrency():
    """Test server handling concurrent requests"""
    print("\n" + "=" * 60)
    print("SERVER CONCURRENCY TEST")
    print("=" * 60)

    import subprocess
    import sys

    # Start server
    proc = subprocess.Popen(
        [sys.executable, "benchmarks/barq_app.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)

    try:
        def make_request(_):
            start = time.perf_counter()
            with urllib.request.urlopen("http://127.0.0.1:8001/cpu", timeout=10) as r:
                r.read()
            return time.perf_counter() - start

        # Sequential requests
        print("\n1. Sequential requests:")
        t0 = time.perf_counter()
        times = [make_request(i) for i in range(4)]
        seq_total = time.perf_counter() - t0
        print(f"   4 requests sequential: {seq_total:.3f}s")
        print(f"   Individual times: {[f'{t:.3f}' for t in times]}")

        # Parallel requests
        print("\n2. Parallel requests (should be ~same as 1 request if truly parallel):")
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            times = list(pool.map(make_request, range(4)))
        par_total = time.perf_counter() - t0
        print(f"   4 requests parallel:   {par_total:.3f}s")
        print(f"   Individual times: {[f'{t:.3f}' for t in times]}")

        print(f"\n   Speedup: {seq_total / par_total:.2f}x")

        if par_total < seq_total * 0.5:
            print("   ✓ SERVER IS HANDLING REQUESTS IN PARALLEL")
        else:
            print("   ✗ SERVER IS SERIALIZING REQUESTS")

        # More parallel requests
        print("\n3. 10 parallel requests to 4-thread server:")
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as pool:
            times = list(pool.map(make_request, range(10)))
        total = time.perf_counter() - t0
        print(f"   Total time: {total:.3f}s")
        print(f"   Expected if parallel (10/4 * ~2ms): ~{10/4 * 0.002:.3f}s")
        print(f"   Throughput: {10 / total:.1f} req/s")

    finally:
        proc.terminate()
        proc.wait()


def test_our_pool():
    """Test our ThreadPool implementation"""
    print("\n" + "=" * 60)
    print("OUR THREAD POOL TEST")
    print("=" * 60)

    from barq.pool import ThreadPool
    import queue

    results = queue.Queue()

    def cpu_task(task_id: int):
        start = time.perf_counter()
        thread_name = threading.current_thread().name
        data = b"test"
        for _ in range(5000):
            data = hashlib.sha256(data).digest()
        elapsed = time.perf_counter() - start
        results.put((task_id, thread_name, elapsed))

    pool = ThreadPool(workers=4)
    pool.start()

    print("\n1. Submit 4 tasks to our pool:")
    t0 = time.perf_counter()
    for i in range(4):
        pool.submit(cpu_task, i)

    # Wait for results
    collected = []
    while len(collected) < 4:
        try:
            collected.append(results.get(timeout=5))
        except:
            break

    total = time.perf_counter() - t0
    print(f"   Total time: {total:.3f}s")
    for task_id, thread, elapsed in sorted(collected):
        print(f"   Task {task_id} on {thread}: {elapsed:.3f}s")

    pool.shutdown()


if __name__ == "__main__":
    test_thread_parallelism()
    test_our_pool()
    test_server_concurrency()
