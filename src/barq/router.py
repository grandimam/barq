import re

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable


@dataclass(slots=True)
class RouteData:
    handler: Callable[..., Any]
    meta: Any
    param_names: list[str]


@dataclass(slots=True)
class RadixNode:
    segment: str = ""
    is_param: bool = False
    param_name: str = ""
    children: dict[str, "RadixNode"] = field(default_factory=dict)
    param_child: "RadixNode | None" = None
    handlers: dict[str, RouteData] = field(default_factory=dict)


class RadixRouter:
    PARAM_RE = re.compile(r"\{(\w+)\}")

    def __init__(self) -> None:
        self.root = RadixNode()

    def add(self, path: str, method: str, handler: Callable[..., Any], meta: Any) -> None:
        segments = self._split_path(path)
        param_names: list[str] = []
        node = self.root

        for segment in segments:
            param_match = self.PARAM_RE.fullmatch(segment)

            if param_match:
                param_name = param_match.group(1)
                param_names.append(param_name)

                if node.param_child is None:
                    node.param_child = RadixNode(
                        segment="*",
                        is_param=True,
                        param_name=param_name,
                    )
                node = node.param_child
            else:
                if segment not in node.children:
                    node.children[segment] = RadixNode(segment=segment)
                node = node.children[segment]

        node.handlers[method] = RouteData(handler, meta, param_names)

    def match(self, path: str, method: str) -> tuple[RouteData, dict[str, str]] | None:
        segments = self._split_path(path)
        params: dict[str, str] = {}

        result = self._match_recursive(self.root, segments, 0, method, params)
        if result:
            return result, params
        return None

    def _match_recursive(
        self,
        node: RadixNode,
        segments: list[str],
        index: int,
        method: str,
        params: dict[str, str],
    ) -> RouteData | None:
        if index == len(segments):
            return node.handlers.get(method)

        segment = segments[index]

        if segment in node.children:
            result = self._match_recursive(
                node.children[segment],
                segments,
                index + 1,
                method,
                params,
            )
            if result:
                return result

        if node.param_child:
            params[node.param_child.param_name] = segment
            result = self._match_recursive(
                node.param_child,
                segments,
                index + 1,
                method,
                params,
            )
            if result:
                return result
            del params[node.param_child.param_name]

        return None

    def _split_path(self, path: str) -> list[str]:
        if path == "/":
            return []
        return [s for s in path.split("/") if s]
