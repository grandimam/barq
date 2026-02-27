import os
import selectors
import socket

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from typing import Callable

from .http import HTTPParser
from .http import write_response
from .types import Request
from .types import Response


class ThreadPool:
    def __init__(self, workers: int | None = None):
        self.num_workers = workers or os.cpu_count() or 4
        self.executor: ThreadPoolExecutor | None = None

    def start(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=self.num_workers)

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self.executor.submit(fn, *args, **kwargs)

    def shutdown(self) -> None:
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)


class SocketReader:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = bytearray()

    def readline(self) -> str:
        while True:
            idx = self.buffer.find(b"\r\n")
            if idx != -1:
                line = self.buffer[:idx].decode("latin-1")
                del self.buffer[:idx + 2]
                return line
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Disconnected")
            self.buffer.extend(chunk)

    def read(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Disconnected")
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:n])
        del self.buffer[:n]
        return data


class Server:
    def __init__(
        self,
        handler: Callable[[Request], Response],
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int | None = None,
    ):
        self.handler = handler
        self.host = host
        self.port = port
        self.pool = ThreadPool(workers)

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        sock.bind((self.host, self.port))
        sock.listen(1024)
        sock.setblocking(False)

        self.pool.start()
        sel = selectors.DefaultSelector()
        sel.register(sock, selectors.EVENT_READ)

        print(f"Barq running at http://{self.host}:{self.port} ({self.pool.num_workers} threads)")

        try:
            while True:
                for key, _ in sel.select(timeout=1.0):
                    if key.fileobj is sock:
                        try:
                            client, _ = sock.accept()
                            client.setblocking(True)
                            self.pool.submit(self._handle, client)
                        except BlockingIOError:
                            pass
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.pool.shutdown()
            sock.close()

    def _handle(self, client: socket.socket) -> None:
        try:
            reader = SocketReader(client)
            raw = HTTPParser(reader).parse()
            request = Request(
                method=raw.method,
                path=raw.path,
                headers=raw.headers,
                query_string=raw.query_string,
                body=raw.body,
            )
            response = self.handler(request)
            write_response(client, response.status_code, response.headers, response.body)
        except Exception:
            write_response(client, 500, {"content-length": "0"}, b"")
        finally:
            client.close()
