import inspect
import re

from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import get_args
from typing import get_origin
from typing import get_type_hints

from pydantic import BaseModel
from pydantic import ValidationError

from .server import Server
from .types import HTTPException
from .types import Middleware
from .types import Request
from .types import Response
from .types import StreamingResponse


class Depends:
    def __init__(self, fn: Callable[..., Any]):
        self.fn = fn


@dataclass(slots=True)
class Route:
    path: str
    method: str
    handler: Callable[..., Any]
    pattern: re.Pattern[str]
    param_names: list[str]


class Router:
    PARAM_RE = re.compile(r"\{(\w+)\}")

    def __init__(self):
        self.routes: list[Route] = []

    def add(self, path: str, method: str, handler: Callable[..., Any]) -> None:
        param_names: list[str] = []
        regex_parts: list[str] = []
        last = 0

        for m in self.PARAM_RE.finditer(path):
            regex_parts.append(re.escape(path[last:m.start()]))
            param_names.append(m.group(1))
            regex_parts.append(f"(?P<{m.group(1)}>[^/]+)")
            last = m.end()

        regex_parts.append(re.escape(path[last:]))
        pattern = re.compile("^" + "".join(regex_parts) + "$")

        self.routes.append(Route(path, method, handler, pattern, param_names))

    def match(self, path: str, method: str) -> tuple[Route, dict[str, str]] | None:
        for route in self.routes:
            if route.method != method:
                continue
            m = route.pattern.match(path)
            if m:
                return route, {k: m.group(k) for k in route.param_names}
        return None


class Barq:
    def __init__(self) -> None:
        self.router = Router()
        self._startup: list[Callable[[], None]] = []
        self._shutdown: list[Callable[[], None]] = []
        self._middlewares: list[Middleware] = []

    def get(self, path: str) -> Callable:
        return self._route(path, "GET")

    def post(self, path: str) -> Callable:
        return self._route(path, "POST")

    def put(self, path: str) -> Callable:
        return self._route(path, "PUT")

    def patch(self, path: str) -> Callable:
        return self._route(path, "PATCH")

    def delete(self, path: str) -> Callable:
        return self._route(path, "DELETE")

    def options(self, path: str) -> Callable:
        return self._route(path, "OPTIONS")

    def head(self, path: str) -> Callable:
        return self._route(path, "HEAD")

    def _route(self, path: str, method: str) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self.router.add(path, method, self._wrap(fn))
            return fn
        return decorator

    def middleware(self, fn: Middleware) -> Middleware:
        self._middlewares.append(fn)
        return fn

    def add_middleware(self, fn: Middleware) -> None:
        self._middlewares.append(fn)

    def on_startup(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._startup.append(fn)
        return fn

    def on_shutdown(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._shutdown.append(fn)
        return fn

    def _wrap(self, fn: Callable) -> Callable[[Request, dict[str, str]], Response | StreamingResponse]:
        sig = inspect.signature(fn)
        hints = get_type_hints(fn, include_extras=True) if hasattr(fn, "__annotations__") else {}

        def handler(request: Request, path_params: dict[str, str]) -> Response | StreamingResponse:
            kwargs = self._resolve(sig, hints, request, path_params)
            result = fn(**kwargs)
            return self._to_response(result)
        return handler

    def _resolve(
        self,
        sig: inspect.Signature,
        hints: dict[str, Any],
        request: Request,
        path_params: dict[str, str],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        cache: dict[Callable, Any] = {}

        for name, param in sig.parameters.items():
            hint = hints.get(name)

            if hint is Request:
                kwargs[name] = request
                continue

            dep = self._get_depends(hint)
            if dep:
                kwargs[name] = self._resolve_dep(dep, request, path_params, cache)
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

    def _resolve_dep(
        self,
        dep: Depends,
        request: Request,
        path_params: dict[str, str],
        cache: dict[Callable, Any],
    ) -> Any:
        if dep.fn in cache:
            return cache[dep.fn]
        sig = inspect.signature(dep.fn)
        hints = get_type_hints(dep.fn, include_extras=True) if hasattr(dep.fn, "__annotations__") else {}
        kwargs = self._resolve(sig, hints, request, path_params)
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

    def _to_response(self, result: Any) -> Response | StreamingResponse:
        if isinstance(result, (Response, StreamingResponse)):
            return result
        if inspect.isgenerator(result):
            return StreamingResponse.json_stream(result)
        if isinstance(result, (BaseModel, dict, list)):
            return Response.json(result)
        if isinstance(result, str):
            return Response.text(result)
        if result is None:
            return Response.empty()
        return Response.json(result)

    def _handle(self, request: Request) -> Response | StreamingResponse:
        def dispatch(req: Request) -> Response | StreamingResponse:
            match = self.router.match(req.path, req.method)
            if not match:
                return Response.json({"detail": "Not Found"}, 404)
            route, params = match
            req.path_params = params
            return route.handler(req, params)

        try:
            handler: Callable[[Request], Response | StreamingResponse] = dispatch
            for mw in reversed(self._middlewares):
                handler = self._wrap_middleware(mw, handler)
            return handler(request)
        except HTTPException as e:
            return Response.json({"detail": e.detail}, e.status_code)
        except ValidationError as e:
            return Response.json({"detail": e.errors()}, 422)
        except Exception:
            return Response.json({"detail": "Internal Server Error"}, 500)

    def _wrap_middleware(
        self,
        mw: Middleware,
        next_handler: Callable[[Request], Response | StreamingResponse],
    ) -> Callable[[Request], Response | StreamingResponse]:
        def wrapped(request: Request) -> Response | StreamingResponse:
            return mw(request, next_handler)
        return wrapped

    def run(self, host: str = "127.0.0.1", port: int = 8000, workers: int | None = None) -> None:
        for fn in self._startup:
            fn()
        try:
            Server(self._handle, host, port, workers).run()
        finally:
            for fn in self._shutdown:
                fn()
