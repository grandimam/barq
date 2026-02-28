import inspect

from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import get_args
from typing import get_origin
from typing import get_type_hints

from pydantic import BaseModel
from pydantic import ValidationError

from .router import RadixRouter
from .router import RouteData
from .server import Server
from .types import HTTPException
from .types import Request
from .types import Response


class Depends:
    def __init__(self, fn: Callable[..., Any]):
        self.fn = fn


@dataclass(slots=True)
class HandlerMeta:
    sig: inspect.Signature
    hints: dict[str, Any]
    params: list[tuple[str, inspect.Parameter, Any]]


class Barq:
    def __init__(self):
        self.router = RadixRouter()
        self._startup: list[Callable[[], None]] = []
        self._dep_meta: dict[Callable, HandlerMeta] = {}

    def get(self, path: str) -> Callable:
        return self._route(path, "GET")

    def post(self, path: str) -> Callable:
        return self._route(path, "POST")

    def put(self, path: str) -> Callable:
        return self._route(path, "PUT")

    def delete(self, path: str) -> Callable:
        return self._route(path, "DELETE")

    def _route(self, path: str, method: str) -> Callable:
        def decorator(fn: Callable) -> Callable:
            meta = self._build_meta(fn)
            self.router.add(path, method, fn, meta)
            return fn
        return decorator

    def on_startup(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._startup.append(fn)
        return fn

    def _build_meta(self, fn: Callable) -> HandlerMeta:
        sig = inspect.signature(fn)
        hints = get_type_hints(fn, include_extras=True) if hasattr(fn, "__annotations__") else {}
        params = [(name, param, hints.get(name)) for name, param in sig.parameters.items()]
        return HandlerMeta(sig, hints, params)

    def _resolve(
        self,
        meta: HandlerMeta,
        request: Request,
        path_params: dict[str, str],
        dep_cache: dict[Callable, Any],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}

        for name, param, hint in meta.params:
            if hint is Request:
                kwargs[name] = request
                continue

            dep = self._get_depends(hint)
            if dep:
                kwargs[name] = self._resolve_dep(dep, request, path_params, dep_cache)
                continue

            if name in path_params:
                kwargs[name] = self._coerce(path_params[name], hint)
                continue

            if hint and isinstance(hint, type) and issubclass(hint, BaseModel):
                kwargs[name] = hint.model_validate(request.json())
                continue

            qval = request.query(name)
            if qval is not None:
                kwargs[name] = self._coerce(qval, hint)
            elif param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default

        return kwargs

    def _get_depends(self, hint: Any) -> Depends | None:
        if isinstance(hint, Depends):
            return hint
        origin = get_origin(hint)
        if origin is not None:
            for arg in get_args(hint):
                if isinstance(arg, Depends):
                    return arg
        return None

    def _get_dep_meta(self, fn: Callable) -> HandlerMeta:
        if fn not in self._dep_meta:
            self._dep_meta[fn] = self._build_meta(fn)
        return self._dep_meta[fn]

    def _resolve_dep(
        self,
        dep: Depends,
        request: Request,
        path_params: dict[str, str],
        cache: dict[Callable, Any],
    ) -> Any:
        if dep.fn in cache:
            return cache[dep.fn]
        meta = self._get_dep_meta(dep.fn)
        kwargs = self._resolve(meta, request, path_params, cache)
        result = dep.fn(**kwargs)
        cache[dep.fn] = result
        return result

    def _coerce(self, val: str, hint: type | None) -> Any:
        if hint is int:
            return int(val)
        if hint is float:
            return float(val)
        if hint is bool:
            return val.lower() in ("true", "1")
        return val

    def _to_response(self, result: Any) -> Response:
        if isinstance(result, Response):
            return result
        if isinstance(result, (BaseModel, dict, list)):
            return Response.json(result)
        if isinstance(result, str):
            return Response.text(result)
        if result is None:
            return Response.empty()
        return Response.json(result)

    def _handle(self, request: Request) -> Response:
        try:
            match = self.router.match(request.path, request.method)
            if not match:
                return Response.json({"detail": "Not Found"}, 404)
            route_data, params = match
            request.path_params = params
            dep_cache: dict[Callable, Any] = {}
            kwargs = self._resolve(route_data.meta, request, params, dep_cache)
            result = route_data.handler(**kwargs)
            return self._to_response(result)
        except HTTPException as e:
            return Response.json({"detail": e.detail}, e.status_code)
        except ValidationError as e:
            return Response.json({"detail": e.errors()}, 422)
        except Exception:
            return Response.json({"detail": "Internal Server Error"}, 500)

    def run(self, host: str = "127.0.0.1", port: int = 8000, workers: int | None = None) -> None:
        for fn in self._startup:
            fn()
        Server(self._handle, host, port, workers).run()
