import json

from dataclasses import dataclass
from dataclasses import field
from typing import Any
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
