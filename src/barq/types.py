import json

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable
from typing import Generator
from typing import Iterator
from urllib.parse import parse_qs

from pydantic import BaseModel


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class HTTPParseError(Exception):
    pass


@dataclass(slots=True)
class Request:
    method: str
    path: str
    headers: dict[str, str]
    path_params: dict[str, str] = field(default_factory=dict)
    query_string: str = ""
    body: bytes = b""
    state: dict[str, Any] = field(default_factory=dict)
    _query: dict[str, list[str]] | None = field(default=None, repr=False)
    _json: Any = field(default=None, repr=False)

    @property
    def query_params(self) -> dict[str, list[str]]:
        if self._query is None:
            self._query = parse_qs(self.query_string)
        return self._query

    def query(self, name: str, default: str | None = None) -> str | None:
        values = self.query_params.get(name)
        return values[0] if values else default

    def json(self) -> Any:
        if self._json is None and self.body:
            self._json = json.loads(self.body)
        return self._json


@dataclass(slots=True)
class Response:
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @classmethod
    def json(cls, data: Any, status_code: int = 200) -> "Response":
        if isinstance(data, BaseModel):
            body = data.model_dump_json().encode()
        elif isinstance(data, list):
            items = [x.model_dump() if isinstance(x, BaseModel) else x for x in data]
            body = json.dumps(items).encode()
        else:
            body = json.dumps(data).encode()

        return cls(
            status_code=status_code,
            headers={"content-type": "application/json", "content-length": str(len(body))},
            body=body,
        )

    @classmethod
    def text(cls, content: str, status_code: int = 200) -> "Response":
        body = content.encode()
        return cls(
            status_code=status_code,
            headers={"content-type": "text/plain", "content-length": str(len(body))},
            body=body,
        )

    @classmethod
    def empty(cls, status_code: int = 204) -> "Response":
        return cls(status_code=status_code, headers={"content-length": "0"})

    @classmethod
    def html(cls, content: str, status_code: int = 200) -> "Response":
        body = content.encode()
        return cls(
            status_code=status_code,
            headers={"content-type": "text/html; charset=utf-8", "content-length": str(len(body))},
            body=body,
        )


@dataclass(slots=True)
class StreamingResponse:
    iterator: Iterator[bytes] | Generator[bytes, None, None]
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    media_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if "content-type" not in self.headers:
            self.headers["content-type"] = self.media_type
        self.headers["transfer-encoding"] = "chunked"

    @classmethod
    def json_stream(
        cls,
        iterator: Iterator[Any] | Generator[Any, None, None],
        status_code: int = 200,
    ) -> "StreamingResponse":
        def generate() -> Generator[bytes, None, None]:
            for item in iterator:
                if isinstance(item, BaseModel):
                    yield item.model_dump_json().encode() + b"\n"
                else:
                    yield json.dumps(item).encode() + b"\n"
        return cls(
            iterator=generate(),
            status_code=status_code,
            media_type="application/x-ndjson",
        )

    @classmethod
    def text_stream(
        cls,
        iterator: Iterator[str] | Generator[str, None, None],
        status_code: int = 200,
    ) -> "StreamingResponse":
        def generate() -> Generator[bytes, None, None]:
            for item in iterator:
                yield item.encode()
        return cls(
            iterator=generate(),
            status_code=status_code,
            media_type="text/plain; charset=utf-8",
        )

    @classmethod
    def sse(
        cls,
        iterator: Iterator[dict[str, Any]] | Generator[dict[str, Any], None, None],
        status_code: int = 200,
    ) -> "StreamingResponse":
        def generate() -> Generator[bytes, None, None]:
            for event in iterator:
                data = event.get("data", "")
                event_type = event.get("event")
                event_id = event.get("id")
                lines: list[str] = []
                if event_id:
                    lines.append(f"id: {event_id}")
                if event_type:
                    lines.append(f"event: {event_type}")
                if isinstance(data, (dict, list)):
                    lines.append(f"data: {json.dumps(data)}")
                else:
                    lines.append(f"data: {data}")
                lines.append("")
                yield "\n".join(lines).encode() + b"\n"
        return cls(
            iterator=generate(),
            status_code=status_code,
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
            media_type="text/event-stream",
        )


Middleware = Callable[["Request", Callable[["Request"], Response | StreamingResponse]], Response | StreamingResponse]


def stream_parallel(
    tasks: list[Callable[[], Any]],
    workers: int | None = None,
) -> Generator[Any, None, None]:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import as_completed

    num_workers = workers or min(len(tasks), os.cpu_count() or 4)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(task): i for i, task in enumerate(tasks)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                yield {"index": idx, "result": result, "error": None}
            except Exception as e:
                yield {"index": idx, "result": None, "error": str(e)}
