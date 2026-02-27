import socket

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import HTTPParseError

if TYPE_CHECKING:
    from .server import SocketReader

STATUS_PHRASES = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
}


@dataclass(slots=True)
class RawRequest:
    method: str
    path: str
    query_string: str
    headers: dict[str, str]
    body: bytes


class HTTPParser:
    def __init__(self, reader: "SocketReader"):
        self.reader = reader

    def parse(self) -> RawRequest:
        line = self.reader.readline()
        method, target, _ = self._parse_request_line(line)
        path, query = self._split_target(target)
        headers = self._parse_headers()
        body = self._read_body(headers)
        return RawRequest(method, path, query, headers, body)

    def _parse_request_line(self, line: str) -> tuple[str, str, str]:
        parts = line.split(" ", 2)
        if len(parts) != 3:
            raise HTTPParseError(f"Bad request line: {line}")
        return parts[0].upper(), parts[1], parts[2]

    def _split_target(self, target: str) -> tuple[str, str]:
        if "?" in target:
            path, query = target.split("?", 1)
            return path, query
        return target, ""

    def _parse_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        while True:
            line = self.reader.readline()
            if not line:
                break
            idx = line.find(":")
            if idx == -1:
                raise HTTPParseError(f"Bad header: {line}")
            headers[line[:idx].lower()] = line[idx + 1:].strip()
        return headers

    def _read_body(self, headers: dict[str, str]) -> bytes:
        length = headers.get("content-length")
        if not length:
            return b""
        return self.reader.read(int(length))


def write_response(sock: socket.socket, status: int, headers: dict[str, str], body: bytes) -> None:
    phrase = STATUS_PHRASES.get(status, "Unknown")
    lines = [f"HTTP/1.1 {status} {phrase}"]
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("")
    head = "\r\n".join(lines).encode("latin-1")
    sock.sendall(head + body)
